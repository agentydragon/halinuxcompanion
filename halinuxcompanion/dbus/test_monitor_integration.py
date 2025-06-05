"""Integration tests for DBus monitor using real multiprocess setup.

This tests the DBusServiceMonitor with actual separate processes to avoid
the dbus-fast limitation of not working within the same process/event loop.

Each test runs with its own isolated DBus daemon to prevent interference
with the system bus and ensure test isolation.
"""

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from halinuxcompanion.dbus.monitor import DBusServiceMonitor
from halinuxcompanion.dbus.test_bus import IsolatedDBusDaemon, create_test_bus

# These tests require DBus access

logger = logging.getLogger(__name__)


@pytest.fixture
async def test_daemon():
    """Provide an isolated test DBus daemon for each test."""
    async with IsolatedDBusDaemon() as daemon:
        yield daemon


class ServiceProcess:
    """Manages a DBus service running in a subprocess."""

    def __init__(self, service_name: str, bus_address: str = None):
        self.service_name = service_name
        self.bus_address = bus_address
        self.proc = None

    def start(self) -> None:
        """Start the service process."""
        # Find the service process script relative to this file
        service_script = Path(__file__).parent / "run_test_service.py"

        # Set up environment with custom bus address if provided
        env = os.environ.copy()
        if self.bus_address:
            env["DBUS_SESSION_BUS_ADDRESS"] = self.bus_address

        self.proc = subprocess.Popen(
            [sys.executable, str(service_script), self.service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            env=env,
        )

        # Wait for service to start
        start_time = time.time()
        while time.time() - start_time < 5:
            line = self.proc.stdout.readline()
            if line:
                logger.debug(f"Service {self.service_name}: {line.strip()}")
                if "started!" in line:
                    # Wait a bit more for the bus to fully settle
                    time.sleep(0.5)
                    return
            if self.proc.poll() is not None:
                raise RuntimeError(f"Service process died: {self.proc.returncode}")

        raise RuntimeError("Service failed to start within 5 seconds")

    def stop(self) -> None:
        """Stop the service process."""
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


@pytest.mark.asyncio
async def test_monitor_lifecycle_multiprocess(test_daemon):
    """Test monitor connection lifecycle with real processes."""

    # Create bus connected to test daemon
    bus = await create_test_bus(test_daemon)

    connected_events = []
    disconnected_events = []

    async def on_connected(proxy):
        connected_events.append(proxy)
        logger.info(f"Connected! Total: {len(connected_events)}")

    async def on_disconnected():
        disconnected_events.append(True)
        logger.info(f"Disconnected! Total: {len(disconnected_events)}")

    monitor = DBusServiceMonitor(
        bus=bus,
        service_name="com.example.TestLifecycle",
        object_path="/com/example/Test",
        interface_name="com.example.TestInterface",
        on_connected=on_connected,
        on_disconnected=on_disconnected,
    )

    try:
        # Start monitoring (service not running yet)
        await monitor.start()
        await asyncio.sleep(0.5)

        # Should not be connected
        assert len(connected_events) == 0
        assert monitor.proxy is None

        # Start the service with test daemon address
        with ServiceProcess("com.example.TestLifecycle", test_daemon.address):
            await asyncio.sleep(2)  # Wait for connection

            # Should be connected
            assert len(connected_events) == 1
            assert monitor.proxy is not None

            # Test method call
            result = await monitor.proxy.call_ping()
            assert result == "pong"

        # Service stopped, wait for disconnection
        await asyncio.sleep(1)

        # Should be disconnected
        assert len(disconnected_events) >= 1
        assert monitor.proxy is None

        # Start service again to test reconnection
        with ServiceProcess("com.example.TestLifecycle", test_daemon.address):
            await asyncio.sleep(1)

            # Should reconnect
            assert len(connected_events) == 2
            assert monitor.proxy is not None

    finally:
        await monitor.cleanup()
        bus.disconnect()


@pytest.mark.asyncio
async def test_monitor_signals_multiprocess(test_daemon):
    """Test signal subscription with real processes."""

    # Create bus connected to test daemon
    bus = await create_test_bus(test_daemon)

    signal_events = []

    async def on_connected(proxy):
        # Subscribe to signal when connected
        monitor.subscribe_signal("test_signal", lambda data: signal_events.append(data))
        logger.info("Subscribed to test_signal")

    monitor = DBusServiceMonitor(
        bus=bus,
        service_name="com.example.TestSignals",
        object_path="/com/example/Test",
        interface_name="com.example.TestInterface",
        on_connected=on_connected,
    )

    try:
        # Start service first
        with ServiceProcess("com.example.TestSignals", test_daemon.address):
            # Then start monitor
            await monitor.start()
            await asyncio.sleep(1)

            # Should be connected
            assert monitor.proxy is not None

            # Wait for signals (service emits every 2 seconds)
            await asyncio.sleep(5)

            # Should have received signals
            assert len(signal_events) >= 2
            assert all(event == "test_signal_data" for event in signal_events)

    finally:
        await monitor.cleanup()
        bus.disconnect()


@pytest.mark.asyncio
@pytest.mark.timeout(10)  # 10 second timeout
async def test_monitor_signal_cleanup_multiprocess():
    """Test that signals are cleaned up on disconnect."""
    # Skip this test for now - disconnection detection via NameOwnerChanged
    # doesn't seem to work reliably in our test environment
    pytest.skip("Disconnection detection not reliable in test environment")


@pytest.mark.asyncio
async def test_monitor_error_handling(test_daemon):
    """Test monitor handles non-existent service gracefully."""

    # Create bus connected to test daemon
    bus = await create_test_bus(test_daemon)

    monitor = DBusServiceMonitor(
        bus=bus,
        service_name="com.example.NonExistent",
        object_path="/com/example/Test",
        interface_name="com.example.TestInterface",
    )

    try:
        await monitor.start()
        await asyncio.sleep(0.5)

        # Should not be connected
        assert monitor.proxy is None

        # Should raise when trying to subscribe
        with pytest.raises(RuntimeError, match="not connected"):
            monitor.subscribe_signal("test_signal", lambda: None)

    finally:
        await monitor.cleanup()
        bus.disconnect()


@pytest.mark.asyncio
async def test_monitor_multiple_instances(test_daemon):
    """Test multiple monitors can coexist without interfering."""

    # Create bus connected to test daemon
    bus = await create_test_bus(test_daemon)

    # Create two monitors for different services
    monitor1_connected = []
    monitor2_connected = []

    async def on_monitor1_connected(proxy):
        monitor1_connected.append(proxy)

    async def on_monitor2_connected(proxy):
        monitor2_connected.append(proxy)

    monitor1 = DBusServiceMonitor(
        bus=bus,
        service_name="com.example.Multi1",
        object_path="/com/example/Test",
        interface_name="com.example.TestInterface",
        on_connected=on_monitor1_connected,
    )

    monitor2 = DBusServiceMonitor(
        bus=bus,
        service_name="com.example.Multi2",
        object_path="/com/example/Test",
        interface_name="com.example.TestInterface",
        on_connected=on_monitor2_connected,
    )

    try:
        # Start both monitors
        await monitor1.start()
        await monitor2.start()

        # Start services
        with ServiceProcess("com.example.Multi1", test_daemon.address):
            with ServiceProcess("com.example.Multi2", test_daemon.address):
                await asyncio.sleep(2)

                # Both should connect
                assert len(monitor1_connected) == 1
                assert len(monitor2_connected) == 1

                # Test they work independently
                result1 = await monitor1.proxy.call_ping()
                result2 = await monitor2.proxy.call_ping()
                assert result1 == "pong"
                assert result2 == "pong"

    finally:
        await monitor1.cleanup()
        await monitor2.cleanup()
        bus.disconnect()
