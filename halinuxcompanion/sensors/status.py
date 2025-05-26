"""Status sensor implementation."""

import logging
from typing import Dict, Optional

from ..sensor_base import BaseSensor, SensorMetadata
from ..dbus import dbus_signal_handler

logger = logging.getLogger(__name__)


class StatusSensor(BaseSensor):
    """System status sensor (power/sleep state)."""

    sensor_type = "binary_sensor"
    config_name = "status"

    def __init__(self):
        """Initialize status sensor."""
        super().__init__()
        self._sleep_state = False
        self._shutdown_state = False
        self._idle_state: Optional[bool] = None

    def get_metadata(self) -> SensorMetadata:
        """Get status sensor metadata."""
        return SensorMetadata(
            unique_id="status",
            name="Status",
            config_name=self.config_name,
            device_class="power",
            icon="mdi:cpu-64-bit",
        )

    @classmethod
    async def discover_sensors(cls) -> list["StatusSensor"]:
        """Discover status sensor - always returns one instance."""
        return [cls()]

    async def update(self) -> None:
        """Update status state and attributes.

        Note: This sensor is primarily updated via D-Bus signals.
        The update method just ensures the state is consistent.
        """
        # State is True when system is on, False when sleeping/shutting down
        self.state = not (self._sleep_state or self._shutdown_state)

        # Update attributes
        self.attributes = {}

        if self._shutdown_state:
            self.attributes["reason"] = "power_off"
        elif self._sleep_state:
            self.attributes["reason"] = "sleep"
        else:
            self.attributes["reason"] = "power_on"

        # Add idle state if known
        if self._idle_state is not None:
            self.attributes["idle"] = "true" if self._idle_state else "false"
        else:
            self.attributes["idle"] = "unknown"

    @dbus_signal_handler("system.login_on_prepare_for_sleep")
    async def on_prepare_for_sleep(self, v: bool) -> None:
        """Handler for system sleep and wake up from sleep events.

        https://www.freedesktop.org/software/systemd/man/org.freedesktop.login1.html

        Args:
            v: True if going to sleep, False if waking up from it
        """
        self._sleep_state = v
        await self.update()

    @dbus_signal_handler("system.login_on_prepare_for_shutdown")
    async def on_prepare_for_shutdown(self, v: bool) -> None:
        """Handler for system shutdown/reboot.

        https://www.freedesktop.org/software/systemd/man/org.freedesktop.login1.html

        Args:
            v: True if shutting down, False if powering on.
        """
        self._shutdown_state = v
        await self.update()

    @dbus_signal_handler("session.screensaver_on_active_changed")
    @dbus_signal_handler("session.gnome_screensaver_on_active_changed")
    async def screensaver_on_active_changed(self, v: bool) -> None:
        """Handler for session screensaver status changes.

        Args:
            v: True if screensaver is active (idle), False otherwise
        """
        self._idle_state = v
        await self.update()

