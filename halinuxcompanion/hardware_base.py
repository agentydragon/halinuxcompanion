"""Base classes for hardware class → hardware piece → sensor hierarchy."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Type, TypeVar

from pydantic import BaseModel, Field

from .hardware_config import HardwareClassConfig
from .units import ureg

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


class StateClass(str, Enum):
    TOTAL_INCREASING = "total_increasing"
    MEASUREMENT = "measurement"
    TOTAL = "total"


class SensorType(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


"""
  - apparent_power
  - conductivity
  - data_rate
  - date
  - distance
  - energy
  - energy_distance
  - enum
  - power_factor
  - pressure
  - reactive_power
  - signal_strength
  - sound_pressure
  - speed
  - timestamp
  - unit_price
  - volume
  """


class DeviceClass(str, Enum):
    BATTERY = "battery"
    TEMPERATURE = "temperature"
    VOLTAGE = "voltage"
    DURATION = "duration"
    DATA_SIZE = "data_size"
    POWER = "power"
    CURRENT = "current"
    ENERGY = "energy"
    FREQUENCY = "frequency"
    SIGNAL_STRENGTH = "signal_strength"
    ENERGY_STORAGE = "energy_storage"
    # ^- validated

    # Add more device classes as needed

    # TODO: biary - validate:
    OPENING = "opening"
    CONNECTIVITY = "connectivity"


"""
- battery - Low battery (on = low)
- battery_charging - Charging status
- co / carbon_monoxide - Carbon monoxide detection
- cold - Cold detection
- door - Door open/closed
- light - Light detection
- lock - Lock open/closed
- moving - Moving/stopped
- opening - Generic opening
- plug - Plugged in status
- power - Power detection
- presence - Home/away
- running - Running status
- tamper - Tamper detection
- update - Update available (deprecated)
- vibration - Vibration detection
- window - Window open/closed
"""


class HardwareSensor(BaseModel):
    """A sensor that belongs to a specific hardware piece."""

    type: SensorType = SensorType.SENSOR
    unique_id: str
    name: str | None = None
    unit_of_measurement: str | None = None
    device_class: DeviceClass | None = None
    state_class: StateClass = StateClass.MEASUREMENT
    icon: str | None = None

    # Sensor state - will be populated by the hardware class
    state: Any = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def state_str(self) -> str:
        """Return the state as a string."""
        if self.state is None or isinstance(self.state, str):
            s = str(self.state)
            if self.unit_of_measurement:
                s += f" {self.unit_of_measurement}"
            return s
        if isinstance(self.state, bool) and self.unit_of_measurement is None:
            return str(self.state).lower()
        assert isinstance(self.state, (int, float))
        q = ureg.Quantity(self.state, self.unit_of_measurement)
        # TODO: would be nice to cut off extra precision
        # this returns e.g.: 49.792443999999996 MB
        return f"{q:~#P}"


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

    config_field: str

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
