"""Uptime sensor implementation."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psutil

from ..sensor_base import BaseSensor, SensorMetadata
from ..utils import format_seconds_to_time

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
            icon="mdi:clock-outline",
        )

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> list["BaseSensor"]:
        """Discover uptime sensor - always returns one instance."""
        return [cls()]

    async def update(self) -> None:
        """Update uptime state."""
        # Get uptime in seconds
        boot_time = psutil.boot_time()
        current_time = time.time()
        uptime_seconds = int(current_time - boot_time)

        # Format uptime as human-readable string
        self.state = format_seconds_to_time(uptime_seconds)

        # Add detailed breakdown in attributes
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60

        self.attributes = {
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "total_seconds": uptime_seconds,
            "boot_time": datetime.fromtimestamp(boot_time, timezone.utc).isoformat()
        }

