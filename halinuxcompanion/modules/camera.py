"""Camera module implementation."""

from __future__ import annotations

import logging
import subprocess
from glob import glob
from subprocess import run

from ..module_base import Module, ModulePiece, PerPieceUpdateMixin, Sensor
from ..module_config import CameraConfig

logger = logging.getLogger(__name__)


class CameraPiece(ModulePiece):
    """Represents a camera device."""

    def __init__(self, module_id: str, device_path: str, state_sensor: Sensor):
        super().__init__(module_id)
        self.device_path = device_path  # TODO: dataclass?
        self.state_sensor = state_sensor

    async def update(self) -> None:
        """Update camera state."""
        try:
            # Check if camera is being used
            result = run(["fuser", self.device_path], capture_output=True, check=False)
            output = result.stdout.decode("utf-8").strip()
            self.state_sensor.set_ok("active" if output else "idle")
        except (OSError, subprocess.CalledProcessError) as e:
            self.state_sensor.set_error(e, f"Failed to check camera state for {self.device_path}")

    def get_sensors(self) -> list[Sensor]:
        """Get list of sensors."""
        return [self.state_sensor]


class CameraModule(PerPieceUpdateMixin, Module):
    """Camera module."""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self.config: CameraConfig = config

    async def discover_sensors(self) -> list[Sensor]:
        """Discover available sensors."""
        devices = glob("/dev/video*")
        self._module_pieces.clear()
        for device in devices:
            # Extract device number from path
            device_name = device.split("/")[-1]
            self._module_pieces.append(
                CameraPiece(
                    device_name,
                    device,
                    state_sensor=Sensor(
                        unique_id=f"camera:{device_name}:state",
                        name="Camera State",
                        icon="mdi:video",
                    ),
                )
            )
        if not self._module_pieces:
            logger.debug("No camera devices found")
            return []
        logger.debug(
            f"Discovered {len(self._module_pieces)} cameras: {', '.join(d.module_id for d in self._module_pieces)}"
        )
        return [piece.state_sensor for piece in self._module_pieces]
