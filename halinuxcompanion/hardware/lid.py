"""Lid hardware class implementation."""

from __future__ import annotations

import glob
import logging
from pathlib import Path

from ..hardware_base import (
    DeviceClass,
    HardwareClass,
    HardwarePiece,
    HardwareSensor,
    PerPieceUpdateMixin,
    SensorType,
)
from ..hardware_config import LidConfig

logger = logging.getLogger(__name__)


class LidPiece(HardwarePiece):
    """Represents a laptop lid."""

    def __init__(self, lid_path: Path, is_closed_sensor: HardwareSensor):
        super().__init__("lid")
        self.lid_path = lid_path
        self.is_closed_sensor = is_closed_sensor

    async def update(self) -> None:
        """Update lid state."""
        if not self.is_closed_sensor:
            return

        try:
            content = self.lid_path.read_text().strip().lower()
        except OSError:
            logger.exception(f"Failed to read lid state from {self.lid_path}")
            self.is_closed_sensor.state = None
            return

        # Parse the state - typical format is "state:      open" or "state:      closed"
        if "open" in content:
            self.is_closed_sensor.state = False  # Lid is open
        elif "closed" in content:
            self.is_closed_sensor.state = True  # Lid is closed
        else:
            logger.warning(f"Unknown lid state format: {content}")
            self.is_closed_sensor.state = None

    def get_sensors(self) -> list[HardwareSensor]:
        """Get list of sensors."""
        return list(filter(None, [self.is_closed_sensor]))


class LidHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Lid hardware class."""

    config_field = "lid"

    def __init__(self, config: LidConfig):
        super().__init__(config)
        self.config: LidConfig = config

    async def discover_sensors(self) -> list[HardwareSensor]:
        """Discover available sensors."""
        self._hardware_pieces.clear()
        for path_str in glob.glob("/proc/acpi/button/lid/LID*/state"):
            path = Path(path_str)
            if not path.exists() or not path.is_file():
                continue
            try:
                path.read_text()
            except OSError:
                logger.error(f"Found unreadable lid state file at {path} - check permissions")  # noqa: TRY400
                continue

            logger.info(f"Found lid state at: {path}")
            self._hardware_pieces.append(
                piece := LidPiece(
                    path,
                    is_closed_sensor=HardwareSensor(
                        unique_id=f"lid:{path}",
                        type=SensorType.BINARY_SENSOR,
                        name="Lid Closed",
                        device_class=DeviceClass.OPENING,
                        icon="mdi:laptop",
                    ),
                )
            )
            return piece.get_sensors()
            # TOOD: what if multiple openings - add all

        logger.info("No laptop lid state sensor found")
        return []
