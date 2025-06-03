import asyncio
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from importlib.resources import files
from json import JSONDecodeError

from aiohttp import ClientError
from aiohttp.web import Request, Response, json_response
from dbus_next.aio import ProxyInterface
from pydantic import BaseModel, ConfigDict

from halinuxcompanion.api import API, Server
from halinuxcompanion.companion import CommandConfig
from halinuxcompanion.dbus import Dbus
from halinuxcompanion.dbus_models import DBusNotification, NotificationHints, UrgencyLevel
from halinuxcompanion.utils import validate_url_scheme

logger = logging.getLogger(__name__)

APP_NAME = "halinuxcompanion"
DEFAULT_TITLE = "Home Assistant"
HA_ICON = files("halinuxcompanion.resources").joinpath("home-assistant-favicon.png")
NO_ACTION = "noAction"


class HAImportance(str, Enum):
    """Home Assistant notification importance."""

    MIN = "min"
    LOW = "low"
    DEFAULT = "default"
    HIGH = "high"
    MAX = "max"


# Map Home Assistant importance levels to D-Bus urgency levels
HA_TO_DBUS_URGENCY = {
    HAImportance.MIN: UrgencyLevel.LOW,
    HAImportance.LOW: UrgencyLevel.LOW,
    HAImportance.DEFAULT: UrgencyLevel.NORMAL,
    HAImportance.HIGH: UrgencyLevel.CRITICAL,
    HAImportance.MAX: UrgencyLevel.CRITICAL,
}
COMMAND_PREFIX = "command_"


class CommandNotification(BaseModel):
    """Model for command notifications sent from Home Assistant."""

    model_config = ConfigDict(frozen=True)

    command_id: str


def _error_response(error: str, message: str, status: int) -> Response:
    return json_response(
        {"error": error, "errorMessage": message},
        status=status,
    )


async def run_subprocess_with_logging(command: list[str], description: str) -> None:
    """Run a subprocess and log any errors that occur.

    Args:
        command: Command and arguments to execute
        description: Description of what the command does for logging
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
    except Exception:
        logger.exception(f"Failed to execute command {description}: {command}")
        return

    if process.returncode != 0:
        logger.error(
            f"Command {description} failed with exit code {process.returncode}. "
            f"Command: {command}, stderr: {stderr.decode().strip()}"
        )
    else:
        logger.debug(f"Command {description} completed successfully")


class NotificationRequestAction(BaseModel):
    action: str
    title: str
    uri: str | None = None

    model_config = ConfigDict(frozen=True)


class NotificationRequestData(BaseModel):
    actions: list[NotificationRequestAction] = field(default_factory=list)
    url: str | None = None
    clickAction: str | None = None  # noqa: N815
    tag: str | None = None
    importance: HAImportance = HAImportance.DEFAULT
    timeout: float | None = None

    model_config = ConfigDict(frozen=True)


class NotificationRequest(BaseModel):
    title: str = DEFAULT_TITLE
    message: str = ""
    data: NotificationRequestData = field(default_factory=NotificationRequestData)

    model_config = ConfigDict(frozen=True)


@dataclass
class Notifier:
    """Class that handles the lifetime of notifications
    1. It receives a notification by registering a handler to the web server spawned by the application.
    2. It transforms the notification to the format dbus uses.
    3. It sets up the proxy object to send dbus notifications, and listen to events related to this notifications.
    4. It sends the notification to dbus.
    5. Listens to the dbus events related to this notification.
    6. When dbus events are generated, it emits the event to Home Assistant (if appropieate).
    7. Some action events perform a local action like opening a url.
    """

    # Required dependencies
    api: API
    push_token: str
    url_program: str
    commands: dict[str, CommandConfig]
    ha_url: str
    server: Server

    # Internal state
    interface: ProxyInterface = field(init=False)
    history: OrderedDict[int, NotificationRequest] = field(default_factory=OrderedDict)
    tagtoid: dict[str, int] = field(default_factory=dict)

    async def setup_dbus(self, dbus: Dbus) -> None:
        """Setup D-Bus interface and callbacks."""
        if not (iface := await dbus.get_interface("org.freedesktop.Notifications")):
            logger.warning("Could not find org.freedesktop.Notifications interface, disabling notifications.")
            return

        self.interface = iface
        self.interface.on_action_invoked(self.on_action)
        self.interface.on_notification_closed(self.on_close)

        self.server.set_notification_handler(self.on_ha_notification)

    # Entrypoint to the Class logic
    async def on_ha_notification(self, request: Request) -> Response:
        """Handles notification POST request by Home Assistant.

        Called by http server when a notification is received.
        Notification is transformed to the format dbus uses, and sent to dbus.
        """
        try:
            json = await request.json()
        except JSONDecodeError:
            return _error_response("invalid_json", "Payload is not valid JSON", status=400)

        if json.pop("push_token", None) != self.push_token:
            return _error_response("push_token_mismatch", "Push token mismatch", status=400)

        try:
            r = NotificationRequest.model_validate(json)
        except ValueError:
            return _error_response("invalid_data", "Invalid payload format", status=400)

        logger.info(f"Received notification: {r}")

        # Check if this is a command notification
        if r.message.startswith(COMMAND_PREFIX):
            command_id = r.message.removeprefix(COMMAND_PREFIX)
            if not (command := self.commands.get(command_id)):
                return _error_response("command_not_found", f"No such command: {command_id}", 404)
            logger.info(f"Executing command {command_id}, name={command.name}")
            asyncio.create_task(run_subprocess_with_logging(command.command, f"notification command {command_id}"))
            return json_response(
                {"success": True, "message": f"Command {command_id} started"},
                status=200,
            )

        # Hints: Importance -> Urgency
        # https://people.gnome.org/~mccann/docs/notification-spec/notification-spec-latest.html#urgency-levels
        # https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-channel-importance
        hints = NotificationHints(urgency=HA_TO_DBUS_URGENCY.get(r.data.importance))

        def _timeout():
            # Timeout, convert seconds to milliseconds
            # Dismiss/clear notification ->
            # Replace and hide it in 1 ms, workaround for dbus notifications
            if r.message == "clear_notification":
                logger.info(f"Clearing {r = }")
                return 1
            if r.data.timeout:
                try:
                    return int(float(r.data.timeout) * 1000)
                except ValueError:
                    logger.warning(f"Invalid timeout={r.data.timeout!r}, using default")
            return -1  # -1 = notification server decides how long to show

        def _replaces_id():
            if not r.data.tag:
                return 0
            if r.data.tag not in self.tagtoid:
                logger.warning(f"Trying to replace unknown notification {r.data.tag}")
                return 0
            logger.info(f"Replacing notification with tag {r.data.tag}")
            return self.tagtoid[r.data.tag]

        def _actions():
            # Actions; Home Assistant actions require some transformation
            # https://companion.home-assistant.io/docs/notifications/actionable-notifications
            # https://people.gnome.org/~mccann/docs/notification-spec/notification-spec-latest.html#basic-design
            actions: list[str] = ["default", "Default"]
            for a in r.data.actions:
                actions.extend([a.action, a.title])
            return actions

        dbus_notification = DBusNotification(
            app_name=APP_NAME,
            replaces_id=_replaces_id(),
            app_icon=str(HA_ICON),
            summary=r.title,
            body=r.message,
            actions=_actions(),
            hints=hints,
            expire_timeout=_timeout(),
        )
        asyncio.create_task(self.dbus_notify(dbus_notification, r))
        return json_response(
            {"success": True, "message": "Notification queued"},
            status=201,
        )

    async def ha_event_trigger(self, event: str, r: NotificationRequest, data={}) -> None:
        """Trigger the Home Assistant event given event type and notification dictionary.

        Actions are first handled in on_action which decides wether to emit the event or not.

        :param event: The event type
        :param notification: The notification dictionary
        """
        data = {"title": r.title, "message": r.message} | r.data.model_dump(mode="json") | data
        for i, a in enumerate(r.data.actions, 1):
            # This is necessary when sending event data on_closed, on_action
            data[f"action_{i}_key"] = a.action
            data[f"action_{i}_title"] = a.title

        try:
            res = await self.api.post("/api/events/" + event, json=data)
            logger.info(f"Sent Home Assistant {event=}, response={res.status}")
        except ClientError:
            # Failing to trigger an event is not fatal.
            logger.exception("Error sending Home Assistant event")

    async def dbus_notify(self, dbus_notification: DBusNotification, r: NotificationRequest) -> None:
        """Sends native dbus notification.

        According to Section: org.freedesktop.Notifications.Notify
        https://people.gnome.org/~mccann/docs/notification-spec/notification-spec-latest.html#protocol

        :param dbus_notification: The DBusNotification object to send
        """
        id = await self.interface.call_notify(  # noqa: A001
            dbus_notification.app_name,
            dbus_notification.replaces_id,
            dbus_notification.app_icon,
            dbus_notification.summary,
            dbus_notification.body,
            dbus_notification.actions,
            dbus_notification.hints.to_dbus_dict(),
            dbus_notification.expire_timeout,
        )
        logger.info(f"Dbus notification dispatched {id=}")

        # If this notification is replacing another, remove the old one
        if dbus_notification.replaces_id != 0:
            self._history_remove(dbus_notification.replaces_id)

        # Add new notification to history
        self.history[id] = r
        if tag := r.data.tag:
            self.tagtoid[tag] = id

    async def on_action(self, id: int, action: str) -> None:
        """Handle DBus notification action event.

        If a notifications is found, and the action is not the default action,
        an event is triggered to home assistant.
        (This is how the android app handles actions).

        :param id: DBus id of the notification
        :param action: The action that was invoked
        """
        logger.info(f"Notification action dbus event received: {id=}, {action=}")
        if not (r := self.history.get(id)):
            logger.info(f"Notification {id=} not in history")
            return

        uri: str | None = None

        if action == "default":
            uri = r.data.url or r.data.clickAction or ""
            # check if uri starts with /lovelace or lovelace using regex
            if re.match(r"^/?lovelace", uri):
                uri = f"{self.ha_url}/{uri.lstrip('/')}"
            # noAction is a special URL that means do nothing when clicked

        elif actions := r.data.actions:
            uri = next(filter(lambda d: d.action == action, actions)).uri
            await self.ha_event_trigger(
                "mobile_app_notification_action",
                r,
                data={"action": action},
            )
        else:
            logger.info(f"{action=} not handled, no uri found in {r=}")
            return  # No action to perform

        # Handle special URI types
        if not uri or uri == NO_ACTION:
            logger.info(f"{action=} URI is {uri}, doing nothing")
            return
        if not self.url_program:
            logger.warning(f"No URL program configured, cannot handle {action=}")
            return
        # Validate URI scheme for security
        if not validate_url_scheme(uri):
            logger.warning(f"{action=} {uri=} scheme not accepted, skipping action")
            return
        logger.info(f"{action=} launching {uri=}")
        asyncio.create_task(
            run_subprocess_with_logging(
                [self.url_program, uri],
                f"{action=} handler for {uri=}",
            )
        )

    def _history_remove(self, id: int) -> None:
        """Remove a notification from history by its DBus id."""
        if not (r := self.history.pop(id, None)):
            logger.warning(f"Notification {id=} not found in history")
            return
        if not r.data.tag:
            return  # No tag to remove
        if (tag := r.data.tag) not in self.tagtoid:
            logger.warning(f"Notification {id=} found in history but not in tag mapping")
            return
        self.tagtoid.pop(tag, None)

    async def on_close(self, id: int, reason: str) -> None:
        """Handles the DBus notification close event

        :param id: DBus id of the notification
        :param reason: Reason the notification was closed
        """
        logger.info(f"Notification closed dbus event received: {id=}, {reason=}")
        if not (r := self.history.get(id)):
            logger.info(f"No notification found for {id=}, doesn't belong to this applicaton")
            return
        # TODO: also send reason?
        await self.ha_event_trigger("mobile_app_notification_cleared", r=r)
        self._history_remove(id)
