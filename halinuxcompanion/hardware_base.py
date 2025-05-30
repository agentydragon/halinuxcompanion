"""Base classes for hardware class → hardware piece → sensor hierarchy."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type, TypeVar

from .hardware_config import HardwareClassConfig, SensorInfo

logger = logging.getLogger(__name__)

# Type variable for sensor data
TSensorData = TypeVar("TSensorData")


@dataclass
class SensorMetadata:
    """Metadata for a sensor instance."""

    name: str
    config_name: str
    icon: str | None = None


class HardwarePiece:
    """Represents a specific piece of hardware (e.g., a specific battery, network interface).

    Optional helper class hardware implementations may use.
    Provides no required interface - implementations define their own.
    """

    def __init__(self, hardware_id: str):
        """Initialize a hardware piece.

        Args:
            hardware_id: Unique identifier for this hardware piece
        """
        self.hardware_id = hardware_id


class HardwareSensor:
    """A sensor that belongs to a specific hardware piece."""

    def __init__(
        self,
        hardware_class: str,
        hardware_id: str,
        sensor_type_name: str,
        sensor_info: SensorInfo,
        hardware_piece: HardwarePiece,
    ):
        """Initialize a hardware sensor.

        Args:
            hardware_class: The hardware class (e.g., "battery", "network")
            hardware_id: The specific hardware piece ID (e.g., "BAT0", "eth0")
            sensor_type_name: The type of sensor (e.g., "charge_level", "tx_bytes")
            sensor_info: SensorInfo object with sensor metadata
            hardware_piece: Optional hardware piece (for naming/metadata only)
        """
        self.hardware_class = hardware_class
        self.hardware_id = hardware_id
        self.sensor_type_name = sensor_type_name
        self.sensor_info = sensor_info
        self._hardware_piece = hardware_piece

        # Sensor state - will be populated by the hardware class
        self.state: Any = None
        self.attributes: Dict[str, Any] = {}

    @property
    def sensor_type(self) -> str:
        """Sensor type for HA (sensor or binary_sensor)"""
        return self.sensor_info.type

    @property
    def unique_id(self) -> str:
        return "_".join([self.hardware_class, self.hardware_id, self.sensor_type_name])

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        """Get the native unit of measurement for this sensor."""
        return self.sensor_info.unit

    @property
    def name(self) -> str:
        # Use device name if available (e.g., for bluetooth devices)
        if (
            self._hardware_piece
            and hasattr(self._hardware_piece, "device_name")
            and self._hardware_piece.device_name
        ):
            display_name = self._hardware_piece.device_name
        else:
            display_name = self.hardware_id
        # Format: "Hardware ID - Sensor Type"
        return f"{display_name} - {self.sensor_info.name}"


class HardwareProvider(ABC):
    """Base class for hardware providers that discover and manage hardware pieces."""

    @abstractmethod
    async def discover_hardware(self) -> List[Any]:
        """Discover available hardware pieces.

        Returns:
            List of hardware piece instances (implementation-defined)
        """
        pass


class HardwareClass(ABC):
    """Base class for a hardware class (e.g., battery, network)."""

    def __init__(self, config: HardwareClassConfig):
        """Initialize hardware class with configuration.

        Args:
            config: Configuration for this hardware class
        """
        self.config = config
        self._hardware_pieces: list[HardwarePiece] = []

    @abstractmethod
    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover all sensors for this hardware class.

        Returns:
            List of sensor instances
        """
        pass

    @abstractmethod
    async def update_all_sensors(self) -> None:
        """Update all sensors for this hardware class.

        This method must be implemented by each hardware class.
        It should populate sensor data for all hardware pieces.
        """
        pass


class PerPieceUpdateMixin:
    """Mixin for hardware classes that update each piece individually.

    This provides a default update_all_sensors implementation that
    calls update() on each hardware piece.

    Subclasses using this mixin must define:
        _hardware_pieces: List[Any] - List of hardware pieces with update() method
    """

    _hardware_pieces: List[Any]  # Must be defined by subclass

    async def update_all_sensors(self) -> None:
        """Update all sensors by updating each hardware piece individually."""
        if not self._hardware_pieces:
            return

        # Update each piece individually
        update_tasks = [piece.update() for piece in self._hardware_pieces]
        await asyncio.gather(*update_tasks)


# Registry for hardware classes
HARDWARE_CLASSES: Dict[str, Type[HardwareClass]] = {}
