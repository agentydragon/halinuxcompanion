"""Lid hardware class implementation."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider, PerPieceUpdateMixin
from ..hardware_config import LidConfig, SensorInfo

logger = logging.getLogger(__name__)

# Common lid state paths in sysfs
LID_STATE_PATHS = [
    "/proc/acpi/button/lid/LID0/state",
    "/proc/acpi/button/lid/LID/state",
    "/proc/acpi/button/lid/LID1/state",
]

LID_SENSORS: Dict[str, SensorInfo] = {
    "is_open": SensorInfo(
        type="binary_sensor",
        name="Lid State",
        device_class="opening",  # True when open, False when closed
        icon="mdi:laptop"
    ),
}


@dataclass
class LidData:
    """Lid sensor data."""
    is_open: bool  # True when open, False when closed


class LidPiece(HardwarePiece[LidData]):
    """Represents a laptop lid."""
    
    def __init__(self, lid_path: Path):
        super().__init__("lid")
        self.lid_path = lid_path
    
    async def _fetch_sensor_data(self) -> Optional[LidData]:
        """Fetch fresh sensor data for this lid."""
        try:
            content = self.lid_path.read_text().strip().lower()
        except (OSError, IOError):
            logger.error(f"Failed to read lid state from {self.lid_path}")
            return None
        
        # Parse the state - typical format is "state:      open" or "state:      closed"
        if "open" in content:
            return LidData(is_open=True)  # Lid is open
        elif "closed" in content:
            return LidData(is_open=False)  # Lid is closed
        else:
            logger.warning(f"Unknown lid state format: {content}")
            return None
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types."""
        return set(LID_SENSORS.keys())
    
    def extract_sensor_value(self, data: LidData, sensor_type: str) -> Any:
        """Extract a specific sensor value from lid data."""
        if sensor_type == "is_open":
            return data.is_open
        return None


class LidProvider(HardwareProvider):
    """Lid hardware provider."""
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover available lid sensors."""
        # Try to find a lid state file
        for path_str in LID_STATE_PATHS:
            path = Path(path_str)
            if not path.exists() or not path.is_file():
                continue
                
            try:
                path.read_text()
            except (OSError, IOError):
                logger.warning(f"Found lid state file at {path} but cannot read it - check permissions")
                continue
                
            logger.info(f"Found lid state at: {path}")
            return [LidPiece(path)]
        
        logger.info("No laptop lid state sensor found")
        return []


class LidHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Lid hardware class."""
    
    hardware_name = "lid"
    sensor_definitions = LID_SENSORS
    
    def __init__(self, config: LidConfig):
        super().__init__(config)
        self.config: LidConfig = config
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = LidProvider()
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        return available_sensors