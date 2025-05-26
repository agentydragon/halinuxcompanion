"""Camera state sensor implementation."""

import logging
from glob import glob
from subprocess import run

from ..sensor_base import BaseSensor, SensorMetadata

logger = logging.getLogger(__name__)


class CameraStateSensor(BaseSensor):
    """Camera state sensor."""

    config_name = "camera_state"

    def __init__(self):
        """Initialize camera state sensor."""
        super().__init__()

    def get_metadata(self) -> SensorMetadata:
        """Get camera state sensor metadata."""
        # Dynamic icon based on state
        icon = "mdi:video" if self.state == "active" else "mdi:video-off"

        return SensorMetadata(
            unique_id="camera_state",
            name="Camera State",
            config_name=self.config_name,
            icon=icon,
        )

    @classmethod
    async def discover_sensors(cls) -> list["CameraStateSensor"]:
        """Discover camera state sensor - always returns one instance."""
        return [cls()]

    async def update(self) -> None:
        """Update camera state."""
        # Get list of /dev/video* devices
        devices = glob("/dev/video*")

        if not devices:
            self.state = "unavailable"
            self.attributes = {}
            return

        # Call fuser to check if any camera is being used
        try:
            result = run(["fuser"] + devices, capture_output=True, check=False)
            output = result.stdout.decode("utf-8").strip()

            logger.debug(f"CameraState fuser output: {output}")

            if output:
                self.state = "active"
            else:
                self.state = "idle"

            self.attributes = {
                "device_count": len(devices),
                "devices": devices,
            }

        except Exception as e:
            logger.error(f"Error checking camera state: {e}")
            self.state = "unavailable"
            self.attributes = {}
