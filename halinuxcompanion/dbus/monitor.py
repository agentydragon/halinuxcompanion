"""DBus service monitoring with automatic reconnection."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from dbus_fast import DBusError, Message, MessageType
from dbus_fast.aio import MessageBus

logger = logging.getLogger(__name__)


async def _noop(**kwargs: Any) -> None:
    """Default no-op callback."""


@dataclass
class DBusServiceMonitor:
    """Handles DBus service lifecycle and signal subscriptions.

    This monitor watches for a DBus service appearing/disappearing and manages
    signal subscriptions automatically. When a service disappears and reappears,
    it will reconnect and resubscribe to signals.

    Args:
        bus: Connected MessageBus instance to use
        service_name: DBus service name to monitor (e.g., "org.bluez")
        object_path: DBus object path to connect to
        interface_name: DBus interface name (required for introspection)
        on_connected: Async callback when service becomes available
        on_disconnected: Async callback when service disappears
    """

    bus: MessageBus
    service_name: str
    object_path: str
    interface_name: str
    on_connected: Callable[[Any], Awaitable[None]] = _noop
    on_disconnected: Callable[[], Awaitable[None]] = _noop
    proxy: Any = None
    _signal_handlers: list[tuple[str, Callable, Callable]] = field(default_factory=list)
    _running: bool = False
    _dbus_interface: Any = None

    async def start(self) -> None:
        """Start monitoring the service."""
        self._running = True

        logger.debug("Starting service monitor")

        # Watch for name owner changes
        logger.debug("Setting up name owner watch...")
        await self._watch_name_owner()

        # Give the watch a moment to be fully registered
        await asyncio.sleep(0.1)

        # Try initial connection
        logger.debug("Trying initial connection...")
        await self._try_connect()

    async def _watch_name_owner(self) -> None:
        """Watch for service name owner changes."""
        # Get the DBus interface for subscribing to signals
        introspection = await self.bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
        dbus_proxy = self.bus.get_proxy_object("org.freedesktop.DBus", "/org/freedesktop/DBus", introspection)
        self._dbus_interface = dbus_proxy.get_interface("org.freedesktop.DBus")

        # Subscribe to NameOwnerChanged signal
        self._dbus_interface.on_name_owner_changed(self._on_name_owner_changed)

    async def _handle_name_owner_changed(self, msg: Message) -> None:
        """Handle NameOwnerChanged signal."""
        # Only handle signals
        if msg.message_type != MessageType.SIGNAL:
            return

        logger.debug(f"Got signal: {msg.member}, body: {msg.body}")
        if msg.member != "NameOwnerChanged" or not msg.body:
            return

        name, old_owner, new_owner = msg.body
        if name != self.service_name:
            return

        if new_owner:
            logger.info(f"Service {name} appeared with owner {new_owner}")
            await self._try_connect()
        else:
            logger.info(f"Service {name} vanished")
            await self._handle_disconnect()

    async def _try_connect(self) -> None:
        """Try to connect to the service."""
        try:
            # Try to introspect directly - it will fail quickly if service doesn't exist
            logger.debug(f"Trying to connect to {self.service_name}...")

            introspection = await self.bus.introspect(self.service_name, self.object_path, timeout=2.0)
            self.proxy = self.bus.get_proxy_object(self.service_name, self.object_path, introspection).get_interface(
                self.interface_name
            )

            logger.info(f"Connected to {self.service_name} at {self.object_path}")
            await self.on_connected(self.proxy)

        except (DBusError, asyncio.TimeoutError) as e:
            # This is normal when service doesn't exist
            logger.debug(f"Service {self.service_name} not available: {type(e).__name__}: {e}")
            await self._handle_disconnect()
        except Exception:
            logger.exception(f"Unexpected error connecting to {self.service_name}")
            await self._handle_disconnect()

    async def _handle_disconnect(self) -> None:
        """Handle service disconnection."""
        # Clean up signal subscriptions
        await self.cleanup_signals()

        # Clear proxy
        self.proxy = None

        # Notify
        await self.on_disconnected()

    def subscribe_signal(
        self,
        signal_name: str,
        handler: Callable,
    ) -> None:
        """Subscribe to a signal on the current proxy.

        Args:
            signal_name: Name of the signal (e.g., "PropertiesChanged")
            handler: Callback function for the signal

        Raises:
            RuntimeError: If not connected to service
        """
        if not self.proxy:
            raise RuntimeError(f"Cannot subscribe to {signal_name}: {self.service_name} not connected")

        # Get the on_ method for subscribing
        on_method = getattr(self.proxy, f"on_{signal_name}", None)
        if not on_method:
            raise RuntimeError(f"No signal {signal_name} on interface")

        # Get the off_ method for unsubscribing
        off_method = getattr(self.proxy, f"off_{signal_name}", None)
        if not off_method:
            raise RuntimeError(f"No off method for signal {signal_name}")

        # Subscribe
        on_method(handler)

        # Track for cleanup
        self._signal_handlers.append((signal_name, handler, off_method))

        logger.debug(f"Subscribed to {signal_name} on {self.service_name}")

    async def cleanup_signals(self) -> None:
        """Clean up all signal subscriptions."""
        for signal_name, handler, off_method in self._signal_handlers:
            try:
                off_method(handler)
                logger.debug(f"Unsubscribed from {signal_name}")
            except Exception as e:
                logger.debug(f"Error unsubscribing from {signal_name}: {e}")

        self._signal_handlers.clear()

    async def cleanup(self) -> None:
        """Clean up all resources."""
        self._running = False

        # Clean up signals
        await self.cleanup_signals()

        # Remove message handler
        if self._name_owner_changed_handler and self.bus:
            self.bus.remove_message_handler(self._name_owner_changed_handler)
            self._name_owner_changed_handler = None

        # Don't disconnect the bus - it's managed externally
        self.proxy = None
