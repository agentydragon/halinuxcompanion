"""Camera hardware class implementation."""

import logging
from dataclasses import dataclass
from glob import glob
from subprocess import run
from typing import Any, Dict, List, Optional

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider, PerPieceUpdateMixin
from ..hardware_config import CameraConfig, SensorInfo

logger = logging.getLogger(__name__)


@dataclass
class CameraData:
    """Camera sensor data."""
    state: str  # "active", "idle", or "unavailable"
    device_path: str


class CameraPiece(HardwarePiece[CameraData]):
    """Represents a camera device."""
    
    def __init__(self, hardware_id: str, device_path: str):
        super().__init__(hardware_id)
        self.device_path = device_path
    
    async def _fetch_sensor_data(self) -> Optional[CameraData]:
        """Fetch fresh sensor data for this camera."""
        try:
            # Check if camera is being used
            result = run(["fuser", self.device_path], capture_output=True, check=False)
            output = result.stdout.decode("utf-8").strip()
            
            state = "active" if output else "idle"
            return CameraData(state=state, device_path=self.device_path)
        except Exception:
            logger.debug(f"Failed to check camera state for {self.device_path}", exc_info=True)
            return CameraData(state="unavailable", device_path=self.device_path)
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types."""
        return {"state"}
    
    def extract_sensor_value(self, data: CameraData, sensor_type: str) -> Any:
        """Extract a specific sensor value from camera data."""
        if sensor_type == "state":
            return data.state
        return None


class CameraProvider(HardwareProvider):
    """Camera hardware provider."""
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover available cameras."""
        devices = glob("/dev/video*")
        pieces = []
        
        for device in devices:
            # Extract device number from path
            device_name = device.split("/")[-1]
            pieces.append(CameraPiece(device_name, device))
        
        if pieces:
            logger.debug(f"Discovered {len(pieces)} camera devices: {', '.join(d.hardware_id for d in pieces)}")
        else:
            logger.debug("No camera devices found")
        
        return pieces


class CameraHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Camera hardware class."""
    
    hardware_name = "camera"
    sensor_definitions = {
        "state": SensorInfo(
            name="Camera State",
            icon="mdi:video"
        )
    }
    
    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self.config: CameraConfig = config
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = CameraProvider()
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        # Always enable state sensor
        return available_sensors