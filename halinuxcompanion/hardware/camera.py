"""Camera hardware class implementation."""

from __future__ import annotations

import logging
from glob import glob
from subprocess import run
from typing import List

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import CameraConfig

logger = logging.getLogger(__name__)


class CameraPiece(HardwarePiece):
    """Represents a camera device."""

    def __init__(
        self, hardware_id: str, device_path: str, state_sensor: HardwareSensor
    ):
        super().__init__(hardware_id)
        self.device_path = device_path  # TODO: dataclass?
        self.state_sensor = state_sensor

    async def update(self) -> None:
        """Update camera state."""
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
        return [self.state_sensor]


class CameraHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Camera hardware class."""

    config_field = "camera"

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self.config: CameraConfig = config
        self._hardware_pieces: list[CameraPiece] = []  # type: ignore[assignment]

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover available sensors."""
        devices = glob("/dev/video*")
        self._hardware_pieces.clear()
        for device in devices:
            # Extract device number from path
            device_name = device.split("/")[-1]
            self._hardware_pieces.append(
                CameraPiece(
                    device_name,
                    device,
                    state_sensor=HardwareSensor(
                        unique_id=f"camera:{device_name}:state",
                        name="Camera State",
                        icon="mdi:video",
                    ),
                )
            )
        if not self._hardware_pieces:
            logger.debug("No camera devices found")
            return []
        logger.debug(
            f"Discovered {len(self._hardware_pieces)} cameras: {', '.join(d.hardware_id for d in self._hardware_pieces)}"
        )
        return [piece.state_sensor for piece in self._hardware_pieces]
