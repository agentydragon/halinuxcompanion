"""Uptime sensor implementation."""

import logging
from datetime import datetime, timezone

import psutil

from ..sensor_base import BaseSensor, SensorMetadata

logger = logging.getLogger(__name__)


class UptimeSensor(BaseSensor):
    """System uptime sensor."""

    config_name = "uptime"

    def __init__(self):
        """Initialize uptime sensor."""
        super().__init__()

    def get_metadata(self) -> SensorMetadata:
        """Get uptime sensor metadata."""
        return SensorMetadata(
            unique_id="uptime",
            name="Uptime",
            config_name=self.config_name,
            device_class="timestamp",
            icon="mdi:clock",
        )

    @classmethod
    async def discover_sensors(cls) -> list["UptimeSensor"]:
        """Discover uptime sensor - always returns one instance."""
        return [cls()]

    async def update(self) -> None:
        """Update uptime state."""
        # Get boot time and convert to ISO format timestamp
        boot_time = psutil.boot_time()
        self.state = datetime.fromtimestamp(boot_time, timezone.utc).isoformat()
        self.attributes = {}

