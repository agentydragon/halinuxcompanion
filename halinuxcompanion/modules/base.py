"""Base classes for sensor modules."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator


class SensorType(str, Enum):
    """Home Assistant sensor types."""

    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


class DeviceClass(str, Enum):
    """Home Assistant sensor device classes."""

    BATTERY = "battery"
    CONNECTIVITY = "connectivity"  # For binary sensors
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
    type: SensorType
    name: str
    state: Any
    attributes: dict[str, Any] = Field(default_factory=dict)
    icon: str | None = None
    unit_of_measurement: str | None = None
    device_class: DeviceClass | None = None
    state_class: StateClass | None = None
    entity_category: EntityCategory | None = None
    disabled: bool = False

    @field_validator("state")
    def validate_state_type(cls, v, info):  # noqa: N805
        """Validate state matches sensor type."""
        sensor_type = info.data.get("type")
        if sensor_type == SensorType.BINARY_SENSOR and v is not None and not isinstance(v, bool):
            raise ValueError(f"Binary sensor state must be boolean, got {type(v).__name__}")
        return v

    @field_validator("device_class")
    def validate_device_class(cls, v, info):  # noqa: N805
        """Validate device class matches sensor type."""
        if not v:
            return v

        sensor_type = info.data.get("type")

        # Define valid combinations
        binary_sensor_classes = {DeviceClass.CONNECTIVITY}

        if sensor_type == SensorType.BINARY_SENSOR and v not in binary_sensor_classes:
            raise ValueError(f"Device class {v} not valid for binary sensor")
        if sensor_type == SensorType.SENSOR and v in binary_sensor_classes:
            raise ValueError(f"Device class {v} not valid for regular sensor")

        return v


class SensorUpdate(BaseModel):
    """A sensor state update.

    For valid keys, see:
    https://developers.home-assistant.io/docs/api/native-app-integration/sensors#updating-a-sensor

    This model maps 1:1 to the Home Assistant Mobile App API format.
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
