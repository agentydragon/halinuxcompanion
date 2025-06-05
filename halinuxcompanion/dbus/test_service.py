"""Test DBus service for testing the monitor."""

import logging

from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method, signal

logger = logging.getLogger(__name__)


class SampleTestInterface(ServiceInterface):
    """A test DBus interface."""

    def __init__(self):
        super().__init__("com.example.TestInterface")
        self._test_property = "initial_value"

    @method()
    def ping(self) -> "s":
        """Simple test method."""
        return "pong"

    @method()
    def echo(self, message: "s") -> "s":
        """Echo back a message."""
        return message

    @signal()
    def test_signal(self) -> "s":
        """Test signal that emits a string."""
        return "test_signal_data"

    def emit_test_signal(self) -> None:
        """Emit the test signal."""
        self.test_signal()

    @dbus_property(access=PropertyAccess.READWRITE)
    def test_property(self) -> "s":
        """A test property."""
        return self._test_property

    @test_property.setter
    def test_property(self, value: "s") -> None:
        """Set test property."""
        self._test_property = value


class SampleDBusService:
    """A controllable test DBus service."""

    def __init__(self, service_name: str = "com.example.TestService"):
        self.service_name = service_name
        self.bus: MessageBus | None = None
        self.interface = SampleTestInterface()
        self._running = False
        self._bus_task = None

    async def start(self) -> None:
        """Start the service and request the name."""
        # Connect to session bus
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()

        # Export the interface
        self.bus.export("/com/example/Test", self.interface)

        # Request the service name
        await self.bus.request_name(self.service_name)

        self._running = True
        logger.info(f"Test service {self.service_name} started")

    async def stop(self) -> None:
        """Stop the service and release the name."""
        if not (self._running and self.bus):
            return
        try:
            # Release the name
            await self.bus.release_name(self.service_name)

            # Unexport the interface
            self.bus.unexport("/com/example/Test", self.interface)

            # Disconnect
            self.bus.disconnect()

        except Exception:
            pass  # Ignore errors during cleanup

        self._running = False
        logger.info(f"Test service {self.service_name} stopped")

    async def emit_test_signal(self) -> None:
        """Emit a test signal."""
        if self._running:
            self.interface.emit_test_signal()

    def is_running(self) -> bool:
        """Check if service is running."""
        return self._running
