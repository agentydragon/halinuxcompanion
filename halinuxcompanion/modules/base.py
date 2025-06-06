"""Base classes for sensor modules."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class SensorType(str, Enum):
    """Home Assistant sensor types."""

    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


class DeviceClass(str, Enum):
    """Home Assistant sensor device classes."""

    BATTERY = "battery"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"
    POWER = "power"
    CURRENT = "current"
    ENERGY = "energy"
    FREQUENCY = "frequency"
    DATA_RATE = "data_rate"
    DATA_SIZE = "data_size"
    DURATION = "duration"
    TIMESTAMP = "timestamp"


class StateClass(str, Enum):
    """Home Assistant sensor state classes."""

    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


class EntityCategory(str, Enum):
    """Home Assistant entity categories."""

    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


class SensorRegistration(BaseModel):
    """Information needed to register a sensor with Home Assistant.

    For valid keys, see:
    https://developers.home-assistant.io/docs/api/native-app-integration/sensors#registering-a-sensor
    """

    unique_id: str
    type: str  # "sensor" or "binary_sensor"
    name: str
    state: Any
    attributes: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None
    unit_of_measurement: str | None = None
    device_class: DeviceClass | None = None
    state_class: StateClass | None = None
    entity_category: EntityCategory | None = None
    disabled: bool = False


class SensorUpdate(BaseModel):
    """A sensor state update.

    For valid keys, see:
    https://developers.home-assistant.io/docs/api/native-app-integration/sensors#updating-a-sensor
    """

    unique_id: str
    icon: str | None = None
    state: Any
    type: str | None = None
    attributes: dict[str, Any] | None = None


class UpdateListener(Protocol):
    """Protocol for sensor update listeners."""

    async def __call__(self, update: SensorUpdate) -> None:
        """Handle a sensor update."""
        ...


class BaseModule(ABC):
    """Base class for all sensor modules."""

    @abstractmethod
    def sensors(self) -> list[SensorRegistration]:
        """Return list of sensors this module provides.

        Called once during initialization to register sensors with Home Assistant.
        """

    @abstractmethod
    async def start(self, update_listener: UpdateListener) -> None:
        """Start the module and begin sending updates.

        Args:
            update_listener: Callback to send sensor updates to.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop the module and clean up resources."""
