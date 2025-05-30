import asyncio
import json
import logging
import re
from collections import OrderedDict
from importlib.resources import files
from typing import Any, Dict, List

from aiohttp import ClientError
from aiohttp.web import Response, json_response
from dbus_next.aio import ProxyInterface
from pydantic import BaseModel, ConfigDict

from halinuxcompanion.api import API, Server
from halinuxcompanion.companion import CommandConfig, Companion
from halinuxcompanion.dbus import Dbus
from halinuxcompanion.dbus_models import (
    DBusNotification,
    NotificationHints,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)

APP_NAME = "halinuxcompanion"
HA = "Home Assistant"
HA_ICON = files("halinuxcompanion.resources").joinpath("home-assistant-favicon.png")

# Map Home Assistant importance levels to D-Bus urgency levels
HA_TO_DBUS_URGENCY = {
    "min": UrgencyLevel.LOW,
    "low": UrgencyLevel.LOW,
    "default": UrgencyLevel.NORMAL,
    "high": UrgencyLevel.CRITICAL,
    "max": UrgencyLevel.CRITICAL,
}

EVENTS_ENPOINT = {
    "closed": "/api/events/mobile_app_notification_cleared",
    "action": "/api/events/mobile_app_notification_action",
}

EMPTY_DICT: Dict[str, Any] = {}
COMMAND_PREFIX = "command_"


class CommandNotification(BaseModel):
    """Model for command notifications sent from Home Assistant."""

    model_config = ConfigDict(frozen=True)

    command_id: str


def _error_response(error: str, message: str, status: int):
    return json_response(
        {"error": error, "errorMessage": message},
        status=status,
    )


def _ok_response():
    return json_response(
        {"success": True, "message": "Notification queued"},
        status=201,
    )


async def run_subprocess_with_logging(command: List[str], description: str) -> None:
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
        stdout, stderr = await process.communicate()
    except Exception:
        logger.error(
            f"Failed to execute command {description}: {command}", exc_info=True
        )
        return

    if process.returncode != 0:
        logger.error(
            f"Command {description} failed with exit code {process.returncode}. "
            f"Command: {command}, stderr: {stderr.decode().strip()}"
        )
    else:
        logger.debug(f"Command {description} completed successfully")


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

    # Only keeping the last 20 notifications and popping everytime a new one is added
    history: OrderedDict[int, dict] = OrderedDict(
        (x, EMPTY_DICT) for x in range(-1, -21, -1)
    )
    tagtoid: Dict[str, int] = {}  # Lookup id from tag
    interface: ProxyInterface
    api: API
    push_token: str
    url_program: str
    commands: Dict[str, CommandConfig]
    ha_url: str

    async def init(
        self, dbus: Dbus, api: API, webserverver: Server, companion: Companion
    ) -> None:
        """Function to initialize the notifier.
        1. Gets the dbus interface to send notifications and listen to events.
        2. Registers an http handler to the webserver for Home Assistant notifications.
        3. Register callbacks for dbus events (on_action_invoked and on_notification_closed).
        4. Keeps a reference to the API for firing events in Home Assistant.
        5. Sets the push_token used to check if the notification is for this device.
        6. Sets the url_program used to open urls.

        :param dbus: The Dbus class abstraction
        """
        # Get the interface
        interface = await dbus.get_interface("org.freedesktop.Notifications")

        if interface is None:
            logger.warning(
                "Could not find org.freedesktop.Notifications interface, disabling notification support."
            )
            return

        self.interface = interface
        # Setup dbus callbacks
        self.interface.on_action_invoked(self.on_action)
        self.interface.on_notification_closed(self.on_close)

        # Setup http server route handler for incoming notifications
        webserverver.app.router.add_route("POST", "/notify", self.on_ha_notification)

        # API and necessary data
        self.api = api
        assert companion.state.push_token, "Companion state must have a push_token"
        self.push_token = companion.state.push_token
        self.url_program = companion.config.services.notifications.url_program
        self.commands = companion.config.services.notifications.commands
        self.ha_url = companion.ha_url

    # Entrypoint to the Class logic
    async def on_ha_notification(self, request) -> Response:
        """Function that handles the notification POST request by Home Assistant.

        This is the only entry point to start logic in this class.
            This function is called by the http server when a notification is received. The notification is transformed
            to the format dbus uses, and sent to dbus.

        :param request: The request object
        :return: The response object
        """
        notification: dict = await request.json()
        push_token = notification.get("push_token")
        logger.info(f"Received notification: {notification}")

        # Check if the notification is for this device
        if push_token != self.push_token:
            logger.error(f"Push token mismatch: {push_token=} != {self.push_token=}")
            return _error_response(
                "push_token_mismatch",
                "Push token does not match the registered token",
                status=400,
            )

        transformed = self.notification_transform(notification)
        if isinstance(transformed, DBusNotification):
            # It's a DBusNotification object
            asyncio.create_task(self.dbus_notify(transformed, notification))
            return _ok_response()
        if isinstance(transformed, CommandNotification):
            command_id = transformed.command_id
            command = self.commands.get(command_id)
            if not command:
                # Got notificatoin command but none defined
                logger.error(
                    f"Received notification command {command_id}, but no command is defined"
                )
                return _error_response("command_not_found", "No such command", 404)
            # It's not a notification, but a command, therefore no dbus_notify
            logger.info(
                f"Executing notification command: {command_id}, name={command.name}"
            )
            asyncio.create_task(
                run_subprocess_with_logging(
                    command.command,
                    f"notification command {command_id}",
                )
            )
        raise ValueError(f"Unknown notification type: {type(transformed)}")

    async def ha_event_trigger(
        self, event: str, action: str = "", notification: dict = {}
    ) -> bool:
        """Function to trigger the Home Assistant event given an event type and notification dictionary.
        Actions are first handled in on_action which decides wether to emit the event or not.

        :param event: The event type
        :param action: The action that was invoked (if any)
        :param notification: The notification dictionary
        :return: True if the event was triggered, False otherwise
        """
        endpoint = EVENTS_ENPOINT[event]

        if not notification:
            return False
        data = {
            "title": notification.get("title", ""),
            "message": notification.get("message", ""),
            **notification.get("event_actions", {}),
            **notification["data"],
        }
        # Replaced by event_actions
        if "actions" in data:
            del data["actions"]

        if event == "action":
            data["action"] = action

        try:
            res = await self.api.post(endpoint, json.dumps(data))
            logger.info(
                f"Sent Home Assistant {event=}, {endpoint=}, response={res.status}"
            )
            return True
        except ClientError:
            logger.error("Error sending Home Assistant event")
        return False

    def notification_transform(
        self, notification: dict
    ) -> DBusNotification | CommandNotification:
        """Function to convert a Home Assistant notification to a dbus notification.
        This is done in a best effort manner, as the homeassistant notification format can't be fully translated.
        This function mutates the notification dict.

        :param notification: The notification to convert (mutated)
        :return: DBusNotification for regular notifications, dict for commands
        """
        # Add the data, avoids the need to check (branching) ahead
        data: dict = notification.setdefault("data", {})
        tag: str = data.setdefault("tag", "")

        # Check if this is a command notification
        if notification["message"].startswith(COMMAND_PREFIX):
            return CommandNotification(
                command_id=notification["message"].removeprefix(COMMAND_PREFIX)
            )

        # Build notification components
        actions: List[str] = ["default", "Default"]
        hints = NotificationHints()
        timeout: int = -1  # -1 means notification server decides how long to show
        replace_id: int = 0

        if data:
            # Actions
            # Home Assistant actions require some transformation
            # https://companion.home-assistant.io/docs/notifications/actionable-notifications
            # https://people.gnome.org/~mccann/docs/notification-spec/notification-spec-latest.html#basic-design

            # Dbus notification structure [id, name, id, name, ...]
            event_actions = {}  # Format the actions as necessary for on_close and on_action events
            counter = 1
            for a in data.get("actions", []):
                actions.extend([a["action"], a["title"]])
                # This is necessary when sending event data on_closed, on_action
                event_actions[f"action_{counter}_key"] = a["action"]
                event_actions[f"action_{counter}_title"] = a["title"]
                counter += 1

            notification["event_actions"] = event_actions

            # Uri for the default action
            uri = data.get("url", "") or data.get("clickAction", "")
            # check if uri starts with /lovelace or lovelace using regex
            if uri and re.match(r"^/?lovelace", uri):
                uri = f"{self.ha_url}/{uri.lstrip('/')}"
            notification["default_action_uri"] = uri

            # Hints:
            # Importance -> Urgency
            # https://people.gnome.org/~mccann/docs/notification-spec/notification-spec-latest.html#urgency-levels
            # https://companion.home-assistant.io/docs/notifications/notifications-basic/#notification-channel-importance
            if "importance" in data:
                hints.urgency = HA_TO_DBUS_URGENCY.get(
                    data["importance"], UrgencyLevel.NORMAL
                )

            # Timeout, convert seconds to milliseconds
            if "timeout" in data:
                try:
                    timeout = int(float(data["timeout"]) * 1000)
                except ValueError:
                    logger.warning(
                        f"Invalid timeout={data['timeout']!r}, using default"
                    )
                    timeout = -1

            # Replaces id:
            # Using the notification tag, check if it should replace an existing notification
            replace_id = self.tagtoid.get(tag, 0)

            # Dismiss/clear notification
            if notification["message"] == "clear_notification":
                logger.info(f"Clearing {notification = }")
                # Replace the notification and hide it in 1 millisecond, workaround for dbus notifications
                timeout = 1

        # Store additional data in notification dict for later use
        notification.update(
            {
                "data": data,
                "is_command": False,
            }
        )

        # Create DBusNotification
        dbus_notification = DBusNotification(
            app_name=APP_NAME,
            replaces_id=replace_id,
            app_icon=str(HA_ICON),
            summary=notification.get("title", HA),
            body=notification.get("message", ""),
            actions=actions,
            hints=hints,
            expire_timeout=timeout,
        )

        logger.debug(f"Converted to DBusNotification: {dbus_notification}")
        return dbus_notification

    async def dbus_notify(
        self, dbus_notification: DBusNotification, original_notification: dict
    ) -> None:
        """Function to send a native dbus notification.
        According to the following link:
            Section  org.freedesktop.Notifications.Notify
            https://people.gnome.org/~mccann/docs/notification-spec/notification-spec-latest.html#protocol

        :param dbus_notification: The DBusNotification object to send
        :param original_notification: The original notification dict for history tracking
        :return: None
        """
        logger.info("Sending dbus notification")

        # Convert hints to D-Bus format
        hints_dict = dbus_notification.hints.to_dbus_dict()

        id = await self.interface.call_notify(
            dbus_notification.app_name,
            dbus_notification.replaces_id,
            dbus_notification.app_icon,
            dbus_notification.summary,
            dbus_notification.body,
            dbus_notification.actions,
            hints_dict,
            dbus_notification.expire_timeout,
        )
        logger.info(f"Dbus notification dispatched {id=}")

        # History management: Add the new notification, and remove the oldest one.
        # Storage
        self.history[id] = original_notification
        tag: str = original_notification["data"].get("tag", None)
        if tag:
            self.tagtoid[tag] = id

        # Removal
        _, old_not = self.history.popitem(last=False)
        otag = old_not.get("data", {}).get("tag", "")
        if otag in self.tagtoid:
            self.tagtoid.pop(otag)

    async def on_action(self, id: int, action: str) -> None:
        """Function to handle the dbus notification action event
        If a notifications is found, and the action is not the default action, an event is triggered to home assistant.
        (This is how the android app handles actions).

        :param id: The dbus id of the notification
        :param action: The action that was invoked
        """
        logger.info(f"Notification action dbus event received: {id=}, {action=}")
        if not (notification := self.history.get(id)):
            logger.info(
                f"No notification found for {id=}, doesn't belong to this application"
            )
            return

        if action == "default":
            uri = notification.get("default_action_uri")
        elif actions := notification["data"].get("actions", []):
            # actions is a list of dictionaries {"action": "turn_off", "title": "Turn off House", "uri": "http://..."}
            uri = next(filter(lambda d: d["action"] == action, actions)).get("uri")
            asyncio.create_task(self.ha_event_trigger("action", action, notification))
        else:
            return  # No action to perform

        if uri and uri.startswith("http") and self.url_program:
            logger.info(f"Launching {action=} {uri=}")
            asyncio.create_task(
                run_subprocess_with_logging(
                    [self.url_program, uri],
                    f"URL handler for action '{action}' with URI '{uri}'",
                )
            )

    async def on_close(self, id: int, reason: str) -> None:
        """Function to handle the dbus notification close event
        Sends the data to ha_event_trigger, where the event is created and sent to Home Assistant.

        :param id: The dbus id of the notification
        :param reason: The reason the notification was closed
        """
        logger.info(f"Notification closed dbus event received: {id=}, {reason=}")
        if notification := self.history.get(id):
            asyncio.create_task(
                self.ha_event_trigger(event="closed", notification=notification)
            )
        else:
            logger.info(
                f"No notification found for {id=}, doesn't belong to this applicaton"
            )
