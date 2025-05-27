"""Laptop lid state sensor implementation."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ..sensor_base import BaseSensor, SensorMetadata

logger = logging.getLogger(__name__)

# Common lid state paths in sysfs
LID_STATE_PATHS = [
    "/proc/acpi/button/lid/LID0/state",
    "/proc/acpi/button/lid/LID/state",
    "/proc/acpi/button/lid/LID1/state",
]


class LidStateSensor(BaseSensor):
    """Laptop lid state sensor."""

    sensor_type = "binary_sensor"
    config_name = "lid_state"

    def __init__(self, lid_path: str = ""):
        """Initialize lid state sensor.

        Args:
            lid_path: Path to the lid state file
        """
        super().__init__()
        self.lid_path = lid_path
        self._available = False

    def get_metadata(self) -> SensorMetadata:
        """Get lid state sensor metadata."""
        return SensorMetadata(
            unique_id="lid_state",
            name="Lid State",
            config_name=self.config_name,
            device_class="opening",  # True when open, False when closed
            icon="mdi:laptop",
        )

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> list["BaseSensor"]:
        """Discover available lid state sensors."""
        # Try to find a lid state file
        for path_str in LID_STATE_PATHS:
            path = Path(path_str)
            if path.exists() and path.is_file():
                try:
                    # Try to read the file to ensure we have permission
                    with open(path, "r") as f:
                        f.read()
                    logger.info(f"Found lid state at: {path}")
                    return [cls(str(path))]
                except (OSError, IOError) as e:
                    logger.debug(f"Cannot read lid state from {path}: {e}")
                    continue

        logger.info("No laptop lid state sensor found")
        return []

    async def update(self) -> None:
        """Update lid state."""
        if not self.lid_path:
            self.state = "unavailable"
            self.attributes = {}
            self._available = False
            return

        try:
            with open(self.lid_path, "r") as f:
                content = f.read().strip()

            # Parse the state - typical format is "state:      open" or "state:      closed"
            if "open" in content.lower():
                self.state = True  # Lid is open
                state_text = "open"
            elif "closed" in content.lower():
                self.state = False  # Lid is closed
                state_text = "closed"
            else:
                # Unknown format
                logger.warning(f"Unknown lid state format: {content}")
                self.state = "unknown"
                state_text = "unknown"

            self._available = True

            # Update icon based on state
            metadata = self.get_metadata()
            if self.state is True:
                metadata.icon = "mdi:laptop"
            elif self.state is False:
                metadata.icon = "mdi:laptop-off"
            else:
                metadata.icon = "mdi:help-circle"

            self.attributes = {
                "state_text": state_text,
                "source": self.lid_path,
            }

        except (OSError, IOError) as e:
            logger.error(f"Failed to read lid state from {self.lid_path}: {e}")
            self.state = "unavailable"
            self.attributes = {"error": str(e)}
            self._available = False