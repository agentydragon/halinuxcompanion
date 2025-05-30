import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

from dbus_next import BusType
from dbus_next.aio import MessageBus, ProxyInterface
from dbus_next.errors import DBusError

logger = logging.getLogger(__name__)

NOTIFICATIONS_INTERFACE = "org.freedesktop.Notifications"
LOGIN_INTERFACE = "org.freedesktop.login1.Manager"
SCREENSAVER_INTERFACE = "org.freedesktop.ScreenSaver"
SCREENSAVER_GNOME_INTERFACE = "org.gnome.ScreenSaver"

# Keep track of subscribed signals
subscribed_signals: List[Tuple[str, Callable]] = []

# Global registry for signal handlers registered via decorator
dbus_signal_handlers: Dict[str, Callable[..., Any]] = {}


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
    ]
}


class Dbus:
    session: MessageBus
    system: MessageBus
    interfaces: Dict[str, ProxyInterface]

    async def init(self) -> None:
        self.system = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self.session = await MessageBus(bus_type=BusType.SESSION).connect()
        self.interfaces = {}

    async def _get_interface(self, i: DbusInterface) -> Optional[ProxyInterface]:
        if i.type == "system":
            bus = self.system
        else:
            bus = self.session
        try:
            introspection = await bus.introspect(i.service, i.path)
            proxy = bus.get_proxy_object(i.service, i.path, introspection)
            return proxy.get_interface(
                i.interface or i.service
            )  # TODO :deduple fallback to service if no interface specified
        except DBusError:
            logger.warning(f"Failed to get D-Bus interface {i.interface} at {i.path}")
            return None

    @lru_cache
    async def get_interface(self, name: str) -> Optional[ProxyInterface]:
        iface = self.interfaces.get(name)
        if iface is not None:
            return iface
        self.interfaces[name] = await self._get_interface(INTERFACES[name])
        return self.interfaces[name]

    async def register_signal(self, signal_alias: str, callback: Callable) -> None:
        """Register a signal handler"""
        # TODO: optimize
        for interface in INTERFACES.values():
            if signal_alias in interface.signals.values():
                iface_name = interface.interface
                signal_name = interface.signals[signal_alias]

        iface = await self.get_interface(iface_name)
        if iface is None:
            logger.warning(
                f"Could not register signal callback for interface:{iface_name}, signal:{signal_name}"
            )
            return
        getattr(iface, signal_name)(callback)
        logger.info(
            f"Registered signal callback for interface:{iface_name}, signal:{signal_name}"
        )
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
        setattr(func, "_dbus_signal_alias", signal_alias)
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
        attr = getattr(sensor, attr_name)
        if callable(attr) and hasattr(attr, "_dbus_signal_alias"):
            signal_alias = attr._dbus_signal_alias
            # Register the bound method
            await dbus_instance.register_signal(signal_alias, attr)
            logger.debug(
                f"Registered D-Bus handler on {sensor.__class__.__name__}.{attr_name} "
                f"for signal {signal_alias}"
            )
