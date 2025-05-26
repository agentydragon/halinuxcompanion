"""CPU sensor implementation."""

import logging
import os
from typing import Dict

import psutil

from ..sensor_base import BaseSensor, SensorMetadata
from ..dbus import dbus_signal_handler

logger = logging.getLogger(__name__)


class CpuSensor(BaseSensor):
    """CPU load sensor."""

    config_name = "cpu"

    def __init__(self):
        """Initialize CPU sensor."""
        super().__init__()
        self._allow_update = True
        self._load_average_supported = os.name == "posix"

    def get_metadata(self) -> SensorMetadata:
        """Get CPU sensor metadata."""
        return SensorMetadata(
            unique_id="cpu_load",
            name="CPU Load",
            config_name=self.config_name,
            device_class="power_factor",
            state_class="measurement",
            unit_of_measurement="%",
            icon="mdi:cpu-64-bit",
        )

    @classmethod
    async def discover_sensors(cls) -> list["CpuSensor"]:
        """Discover CPU sensor - always returns one instance."""
        return [cls()]

    async def update(self) -> None:
        """Update CPU state and attributes."""
        if not self._allow_update:
            self.state = "unavailable"
            return

        # Get CPU percentage
        self.state = psutil.cpu_percent()

        # Update attributes
        self.attributes = {
            "cpu_count": psutil.cpu_count(logical=False),
            "cpu_logical_count": psutil.cpu_count(),
        }

        # Add load average on POSIX systems
        if self._load_average_supported:
            load_avg = psutil.getloadavg()
            self.attributes.update(
                {
                    "load_1": load_avg[0],
                    "load_5": load_avg[1],
                    "load_15": load_avg[2],
                }
            )

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

