"""Test DBus daemon management for isolated testing."""

import subprocess
import tempfile
import time
from pathlib import Path

from dbus_fast import BusType
from dbus_fast.aio import MessageBus


class IsolatedDBusDaemon:
    """Manages an isolated DBus daemon for testing."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.address: str | None = None
        self.temp_dir: tempfile.TemporaryDirectory | None = None

    def start(self) -> str:
        """Start the test DBus daemon and return its address."""
        # Create temporary directory for daemon files
        self.temp_dir = tempfile.TemporaryDirectory(prefix="test_dbus_")
        temp_path = Path(self.temp_dir.name)

        # Create config file for isolated daemon
        config_file = temp_path / "test-dbus.conf"
        config_file.write_text("""
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir=/tmp</listen>

  <policy context="default">
    <!-- Allow everything to be sent -->
    <allow send_destination="*" eavesdrop="true"/>
    <!-- Allow everything to be received -->
    <allow eavesdrop="true"/>
    <!-- Allow anyone to own anything -->
    <allow own="*"/>
  </policy>
</busconfig>
        """)

        # Start dbus-daemon with our config
        self.proc = subprocess.Popen(
            ["dbus-daemon", "--nofork", "--config-file", str(config_file), "--print-address"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Read the address
        address_line = self.proc.stdout.readline().strip()
        if not address_line:
            raise RuntimeError("Failed to get DBus daemon address")

        self.address = address_line

        # Give daemon time to fully start
        time.sleep(0.1)

        # Verify it's running
        if self.proc.poll() is not None:
            stderr = self.proc.stderr.read()
            raise RuntimeError(f"DBus daemon died immediately: {stderr}")

        return self.address

    def stop(self):
        """Stop the test DBus daemon."""
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

        if self.temp_dir:
            self.temp_dir.cleanup()

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    async def __aenter__(self):
        """Async context manager entry."""
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.stop()


async def create_test_bus(daemon: IsolatedDBusDaemon) -> MessageBus:
    """Create a message bus connected to the test daemon."""
    if not daemon.address:
        raise RuntimeError("Test daemon not started")

    # Create bus with custom address
    bus = MessageBus(bus_address=daemon.address, bus_type=BusType.SESSION)
    await bus.connect()
    return bus
