"""Base classes for module → module piece → sensor hierarchy."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

import pint
from pydantic import BaseModel, Field

from .module_config import ModuleConfig

# Initialize the unit registry
ureg = pint.UnitRegistry()
# Home Assistant unit definitions
ureg.define("percent = 0.01 * dimensionless = %")

logger = logging.getLogger(__name__)

# Type variable for sensor data
TSensorData = TypeVar("TSensorData")


@dataclass
class ModulePiece:
    """Represents a specific piece of a module (e.g., a specific battery, network interface).

    Optional helper class module implementations may use.
    Provides no required interface - implementations define their own.
    """

    module_id: str  # Unique identifier for this module piece


class StateClass(str, Enum):
    TOTAL_INCREASING = "total_increasing"
    MEASUREMENT = "measurement"
    TOTAL = "total"


class SensorType(str, Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


# TODO: Additional device classes to consider implementing:
# - apparent_power, conductivity, data_rate, date, distance, energy, energy_distance
# - enum, power_factor, pressure, reactive_power, signal_strength, sound_pressure
# - speed, timestamp, unit_price, volume


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


# TODO: Additional binary sensor device classes to consider implementing:
# - battery - Low battery (on = low)
# - battery_charging - Charging status
# - co / carbon_monoxide - Carbon monoxide detection
# - cold - Cold detection
# - door - Door open/closed
# - light - Light detection
# - lock - Lock open/closed
# - moving - Moving/stopped
# - opening - Generic opening
# - plug - Plugged in status
# - power - Power detection
# - presence - Home/away
# - running - Running status
# - tamper - Tamper detection
# - update - Update available (deprecated)
# - vibration - Vibration detection
# - window - Window open/closed


class Sensor(BaseModel):
    """A sensor that belongs to a specific module piece."""

    type: SensorType = SensorType.SENSOR
    unique_id: str
    name: str | None = None
    unit_of_measurement: str | None = None
    device_class: DeviceClass | None = None
    state_class: StateClass | None = StateClass.MEASUREMENT
    icon: str | None = None
    options: list[str] | None = None  # For enum sensors

    # Sensor state - will be populated by the module
    state: Any = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    def set_error(self, error: Exception, log_message: str | None = None) -> None:
        """Set the sensor to error state.

        Args:
            error: The exception that occurred
            log_message: Optional custom log message
        """
        if log_message:
            logger.error(f"{log_message}: {error}")
        else:
            logger.error(f"Sensor {self.unique_id} error: {error}")

        self.state = None
        self.error = str(error)
        self.attributes["error"] = str(error)  # Also in attributes for visibility

    def clear_error(self) -> None:
        """Clear any error state from the sensor."""
        self.error = None
        self.attributes.pop("error", None)

    def set_ok(self, value: Any) -> None:
        """Set the sensor to an OK state with the given value.

        This automatically clears any error state.

        Args:
            value: The sensor value
        """
        self.state = value
        self.clear_error()

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

    def to_registration_dict(self) -> dict[str, Any]:
        """Convert sensor to registration payload for Home Assistant."""
        result = {
            "attributes": self.attributes,
            "device_class": self.device_class,
            "icon": self.icon,
            "name": self.name,
            "state": self.state,
            "type": self.type,
            "unique_id": self.unique_id,
            "unit_of_measurement": self.unit_of_measurement,
            "entity_category": None,  # TODO: support entity_category
        }
        # Only include state_class if it's not None
        if self.state_class is not None:
            result["state_class"] = self.state_class
        # Include options for enum sensors
        if self.options is not None:
            result["options"] = self.options
        return result


class HardwareProvider(ABC):
    """Base class for module providers that discover and manage module pieces."""

    @abstractmethod
    async def discover_module_pieces(self) -> list[Any]:
        """Discover available module pieces.

        Returns:
            List of module piece instances (implementation-defined)
        """


class Module(ABC):
    """Base class for a module (e.g., battery, network)."""

    def __init__(self, config: ModuleConfig):
        """Initialize module with configuration.

        Args:
            config: Configuration for this module
        """
        self.config = config
        self._module_pieces: list[ModulePiece] = []

    @abstractmethod
    async def discover_sensors(self) -> list[Sensor]:
        """Discover all sensors for this module.

        Returns:
            List of sensor instances
        """

    @abstractmethod
    async def update_all_sensors(self) -> None:
        """Update all sensors for this module.

        This method must be implemented by each module.
        It should populate sensor data for all module pieces.
        """


class PerPieceUpdateMixin:
    """Mixin for modules that update each piece individually.

    This provides a default update_all_sensors implementation that
    calls update() on each module piece.

    Subclasses using this mixin must define:
        _module_pieces: List[Any] - List of module pieces with update() method
    """

    _module_pieces: list[Any]  # Must be defined by subclass

    async def update_all_sensors(self) -> None:
        """Update all sensors by updating each module piece individually."""
        if not self._module_pieces:
            return

        # Update each piece individually
        update_tasks = [piece.update() for piece in self._module_pieces]
        await asyncio.gather(*update_tasks)


# Registry for module classes
HARDWARE_CLASSES: dict[str, type[Module]] = {}
