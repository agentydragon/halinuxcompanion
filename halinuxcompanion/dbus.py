import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dbus_next import BusType
from dbus_next.aio import MessageBus, ProxyInterface
from dbus_next.errors import DBusError

logger = logging.getLogger(__name__)

NOTIFICATIONS_INTERFACE = "org.freedesktop.Notifications"
LOGIN_INTERFACE = "org.freedesktop.login1.Manager"
SCREENSAVER_INTERFACE = "org.freedesktop.ScreenSaver"
SCREENSAVER_GNOME_INTERFACE = "org.gnome.ScreenSaver"

# Keep track of subscribed signals
subscribed_signals: list[tuple[str, Callable]] = []

# Global registry for signal handlers registered via decorator
dbus_signal_handlers: dict[str, Callable[..., Any]] = {}


@dataclass
class DbusInterface:
    type: str
    service: str
    path: str
    signals: dict[str, str]
    interface: str | None = None

    def __post_init__(self):
        if not self.interface:
            self.interface = self.service


PREPARE_FOR_SLEEP = "systemd.login_on_prepare_for_sleep"
PREPARE_FOR_SHUTDOWN = "systemd.login_on_prepare_for_shutdown"
SCREENSAVER_ON_ACTIVE_CHANGED = "session.screensaver_on_active_changed"
GNOME_SCREENSAVER_ON_ACTIVE_CHANGED = "session.gnome_screensaver_on_active_changed"
NOTIFICATION_ON_ACTION_INVOKED = "session.notification_on_action_invoked"
NOTIFICATION_ON_NOTIFICATION_CLOSED = "session.notification_on_notification_closed"

INTERFACES = {
    interface.interface: interface
    for interface in [
        DbusInterface(
            type="system",
            service="org.freedesktop.login1",
            path="/org/freedesktop/login1",
            interface=LOGIN_INTERFACE,
            signals={
                "on_prepare_for_sleep": PREPARE_FOR_SLEEP,
                "on_prepare_for_shutdown": PREPARE_FOR_SHUTDOWN,
            },
        ),
        DbusInterface(
            type="session",
            service=SCREENSAVER_INTERFACE,
            path="/org/freedesktop/ScreenSaver",
            signals={"on_active_changed": SCREENSAVER_ON_ACTIVE_CHANGED},
        ),
        DbusInterface(
            type="session",
            service=SCREENSAVER_GNOME_INTERFACE,
            path="/org/gnome/ScreenSaver",
            signals={"on_active_changed": GNOME_SCREENSAVER_ON_ACTIVE_CHANGED},
        ),
        DbusInterface(
            type="session",
            service=NOTIFICATIONS_INTERFACE,
            path="/org/freedesktop/Notifications",
            signals={
                "on_action_invoked": NOTIFICATION_ON_ACTION_INVOKED,
                "on_notification_closed": NOTIFICATION_ON_NOTIFICATION_CLOSED,
            },
        ),
    ]
}


class Dbus:
    session: MessageBus
    system: MessageBus
    interfaces: dict[str, ProxyInterface]

    def __init__(self, session: MessageBus, system: MessageBus):
        self.session = session
        self.system = system
        self.interfaces = {}

    @classmethod
    async def create(cls) -> "Dbus":
        """Create and initialize a new Dbus instance."""
        system = await MessageBus(bus_type=BusType.SYSTEM).connect()
        session = await MessageBus(bus_type=BusType.SESSION).connect()
        return cls(session=session, system=system)

    async def _get_interface(self, i: DbusInterface) -> ProxyInterface | None:
        bus = self.system if i.type == "system" else self.session
        try:
            introspection = await bus.introspect(i.service, i.path)
            proxy = bus.get_proxy_object(i.service, i.path, introspection)
            # TODO :deduple fallback to service if no interface specified
            return proxy.get_interface(i.interface or i.service)
        except DBusError:
            logger.warning(f"Failed to get D-Bus interface {i.interface} at {i.path}")
            return None

    async def get_interface(self, name: str) -> ProxyInterface | None:
        if iface := self.interfaces.get(name):
            return iface
        if interface := await self._get_interface(INTERFACES[name]):
            self.interfaces[name] = interface
        return interface

    async def register_signal(self, signal_alias: str, callback: Callable) -> None:
        """Register a signal handler"""
        # TODO: optimize
        iface_name: str | None = None
        signal_name: str | None = None
        for interface in INTERFACES.values():
            if signal_alias in interface.signals.values():
                iface_name = interface.interface
                signal_name = interface.signals[signal_alias]
                break

        if iface_name is None or signal_name is None:
            logger.warning(f"Unknown signal alias: {signal_alias}")
            return

        if not (iface := await self.get_interface(iface_name)):
            logger.warning(f"Could not register signal callback for interface:{iface_name}, signal:{signal_name}")
            return
        getattr(iface, signal_name)(callback)
        logger.info(f"Registered signal callback for interface:{iface_name}, signal:{signal_name}")
        subscribed_signals.append((signal_alias, callback))


def dbus_signal_handler(signal_alias: str):
    """Decorator to mark a method as a D-Bus signal handler.

    Args:
        signal_alias: The signal alias, e.g., "system.login_on_prepare_for_sleep"

    Example:
        @dbus_signal_handler("system.login_on_prepare_for_sleep")
        async def handle_sleep(self, active: bool):
            if active:
                self.state = "sleeping"
    """

    def decorator(func: Callable) -> Callable:
        # Mark the function with metadata instead of registering immediately
        # This allows us to register bound methods later
        func._dbus_signal_alias = signal_alias  # type: ignore[attr-defined]
        return func

    return decorator


async def register_sensor_dbus_handlers(sensor: Any, dbus_instance: "Dbus") -> None:
    """Register all D-Bus signal handlers found on a sensor instance.

    Args:
        sensor: The sensor instance to scan for handlers
        dbus_instance: The D-Bus connection instance
    """
    # Find all methods with the _dbus_signal_alias attribute
    for attr_name in dir(sensor):
        # Skip special attributes that might not be accessible
        if attr_name.startswith("__") and attr_name.endswith("__"):
            continue
        try:
            attr = getattr(sensor, attr_name)
        except AttributeError:
            logger.warning(f"Attribute {attr_name} not found on {sensor.__class__.__name__}")
            continue
        if callable(attr) and hasattr(attr, "_dbus_signal_alias"):
            signal_alias = attr._dbus_signal_alias
            # Register the bound method
            await dbus_instance.register_signal(signal_alias, attr)
            logger.debug(
                f"Registered D-Bus handler on {sensor.__class__.__name__}.{attr_name} for signal {signal_alias}"
            )
