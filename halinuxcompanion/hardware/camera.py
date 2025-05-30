"""Camera hardware class implementation."""

from __future__ import annotations

import logging
from glob import glob
from subprocess import run
from typing import List, Optional

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareProvider,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import CameraConfig, SensorInfo

logger = logging.getLogger(__name__)


class CameraPiece(HardwarePiece):
    """Represents a camera device."""

    def __init__(self, hardware_id: str, device_path: str):
        super().__init__(hardware_id)
        self.device_path = device_path
        self.state_sensor: Optional[HardwareSensor] = None

    async def update(self) -> None:
        """Update camera state."""
        if not self.state_sensor:
            return
        try:
            # Check if camera is being used
            result = run(["fuser", self.device_path], capture_output=True, check=False)
            output = result.stdout.decode("utf-8").strip()
            self.state_sensor.state = "active" if output else "idle"
        except Exception:
            logger.debug(
                f"Failed to check camera state for {self.device_path}", exc_info=True
            )
            self.state_sensor.state = "unavailable"

    def get_sensors(self) -> List[HardwareSensor]:
        """Get list of sensors."""
        return list(filter(None, [self.state_sensor]))


class CameraProvider(HardwareProvider):
    """Camera hardware provider."""

    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover available cameras."""
        devices = glob("/dev/video*")
        pieces: List[HardwarePiece] = []

        for device in devices:
            # Extract device number from path
            device_name = device.split("/")[-1]
            pieces.append(CameraPiece(device_name, device))

        if pieces:
            logger.debug(
                f"Discovered {len(pieces)} camera devices: {', '.join(d.hardware_id for d in pieces)}"
            )
        else:
            logger.debug("No camera devices found")

        return pieces


class CameraHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Camera hardware class."""

    hardware_class = "camera"
    config_field = "camera"

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self.config: CameraConfig = config
        self._hardware_pieces: list[CameraPiece] = []  # type: ignore[assignment]

    async def get_provider(self) -> HardwareProvider:
        return CameraProvider()

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover available sensors."""
        provider = await self.get_provider()
        pieces = await provider.discover_hardware()
        self._hardware_pieces = pieces

        # Create sensors for each camera
        for piece in pieces:
            piece.state_sensor = HardwareSensor(
                hardware_class=self.hardware_class,
                hardware_id=piece.hardware_id,
                sensor_type_name="state",
                sensor_info=SensorInfo(name="Camera State", icon="mdi:video"),
                hardware_piece=piece,
            )
        return [piece.state_sensor for piece in pieces]
