"""Memory sensor implementation."""

import logging
from typing import Dict, List

import psutil

from ..sensor_base import BaseSensor, SensorMetadata
from ..dbus import dbus_signal_handler

logger = logging.getLogger(__name__)


class MemorySensor(BaseSensor):
    """Memory usage sensor."""

    config_name = "memory"

    def __init__(self):
        """Initialize memory sensor."""
        super().__init__()
        self._allow_update = True

    def get_metadata(self) -> SensorMetadata:
        """Get memory sensor metadata."""
        return SensorMetadata(
            unique_id="memory_usage",
            name="Memory Load",
            config_name=self.config_name,
            device_class="power_factor",
            state_class="measurement",
            unit_of_measurement="%",
            icon="mdi:memory",
        )

    @classmethod
    async def discover_sensors(cls) -> List["MemorySensor"]:
        """Discover memory sensor - always returns one instance."""
        return [cls()]

    async def update(self) -> None:
        """Update memory state and attributes."""
        if not self._allow_update:
            self.state = "unavailable"
            return

        # Get memory information
        memory = psutil.virtual_memory()

        # Calculate percentage used
        self.state = round((memory.total - memory.available) / memory.total * 100, 1)

        # Update attributes (convert to KB)
        self.attributes = {
            "total": memory.total / 1024,
            "available": memory.available / 1024,
            "used": memory.used / 1024,
            "free": memory.free / 1024,
        }

    @dbus_signal_handler("system.login_on_prepare_for_sleep")
    async def on_prepare_for_sleep(self, v: bool) -> None:
        """Handler for system sleep and wake up from sleep events.

        https://www.freedesktop.org/software/systemd/man/org.freedesktop.login1.html

        Args:
            v: True if going to sleep, False if waking up from it
        """
        self._allow_update = not v
        if v:
            self.state = "unavailable"

    @dbus_signal_handler("system.login_on_prepare_for_shutdown")
    async def on_prepare_for_shutdown(self, v: bool) -> None:
        """Handler for system shutdown/reboot.

        https://www.freedesktop.org/software/systemd/man/org.freedesktop.login1.html

        Args:
            v: True if shutting down, False if powering on.
        """
        self._allow_update = not v
        if v:
            self.state = "unavailable"

