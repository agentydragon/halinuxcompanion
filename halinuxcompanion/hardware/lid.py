"""Lid hardware class implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from ..hardware_base import (
    HardwareClass,
    HardwarePiece,
    HardwareProvider,
    HardwareSensor,
    PerPieceUpdateMixin,
)
from ..hardware_config import LidConfig, SensorInfo

logger = logging.getLogger(__name__)

# Common lid state paths in sysfs
LID_STATE_PATHS = [
    "/proc/acpi/button/lid/LID0/state",
    "/proc/acpi/button/lid/LID/state",
    "/proc/acpi/button/lid/LID1/state",
]


class LidPiece(HardwarePiece):
    """Represents a laptop lid."""

    def __init__(self, lid_path: Path):
        super().__init__("lid")
        self.lid_path = lid_path
        self.is_closed_sensor: HardwareSensor

    async def update(self) -> None:
        """Update lid state."""
        try:
            content = self.lid_path.read_text().strip().lower()
        except (OSError, IOError):
            logger.error(f"Failed to read lid state from {self.lid_path}")
            self.is_closed_sensor.state = None
            return

        # Parse the state - typical format is "state:      open" or "state:      closed"
        if "open" in content:
            is_closed = False  # Lid is open
        elif "closed" in content:
            is_closed = True  # Lid is closed
        else:
            logger.warning(f"Unknown lid state format: {content}")
            return

        if self.is_closed_sensor:
            self.is_closed_sensor.state = is_closed

    def get_sensors(self) -> List[HardwareSensor]:
        """Get list of sensors."""
        return list(filter(None, [self.is_closed_sensor]))


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
                logger.error(
                    f"Found lid state file at {path} but cannot read it - check permissions"
                )
                continue

            logger.info(f"Found lid state at: {path}")
            return [LidPiece(path)]

        logger.info("No laptop lid state sensor found")
        return []


class LidHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Lid hardware class."""

    hardware_class = "lid"
    config_field = "lid"

    def __init__(self, config: LidConfig):
        super().__init__(config)
        self.config: LidConfig = config
        self._hardware_pieces: list[LidPiece] = []  # type: ignore[assignment]

    async def get_provider(self) -> HardwareProvider:
        return LidProvider()

    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover available sensors."""
        provider = await self.get_provider()
        pieces = await provider.discover_hardware()
        self._hardware_pieces = pieces

        if not pieces:
            return []

        # Lid is a singleton
        piece = pieces[0]

        piece.is_closed_sensor = HardwareSensor(
            hardware_class=self.hardware_class,
            hardware_id=piece.hardware_id,
            sensor_type_name="is_closed",
            sensor_info=SensorInfo(
                type="binary_sensor",
                name="Lid Closed",
                device_class="opening",
                icon="mdi:laptop",
            ),
            hardware_piece=piece,
        )

        return piece.get_sensors()
