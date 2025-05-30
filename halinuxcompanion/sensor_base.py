"""Base classes for sensor implementation with proper inheritance and discovery."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, Optional, Type, Union

logger = logging.getLogger(__name__)


@dataclass
class SensorMetadata:
    """Metadata for a sensor instance."""

    unique_id: str
    name: str
    config_name: str
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    icon: Optional[str] = None
    entity_category: Optional[str] = None
    native_unit_of_measurement: Optional[str] = None


class BaseSensor(ABC):
    """Abstract base class for all sensors.

    Subclasses should implement:
    - discover_sensors() to find available sensors of this type
    - update() to update the sensor state
    - Optionally override get_metadata() for dynamic metadata
    """

    # Class-level configuration
    sensor_type: ClassVar[str] = "sensor"
    config_name: ClassVar[str]  # e.g., "battery_level"

    # Registry of all sensor classes
    _registry: ClassVar[Dict[str, Type["BaseSensor"]]] = {}

    def __init__(
        self,
        instance_id: str = "",
        unique_id: Optional[str] = None,
        name: Optional[str] = None,
        device_class: Optional[str] = None,
        state_class: Optional[str] = None,
        unit_of_measurement: Optional[str] = None,
        native_unit_of_measurement: Optional[str] = None,
        icon: Optional[str] = None,
        entity_category: Optional[str] = None,
    ):
        """Initialize a sensor instance.

        Args:
            instance_id: Unique identifier for this instance (e.g., "BAT0" for battery)
            unique_id: Unique ID override
            name: Name override
            device_class: Device class override
            state_class: State class override
            unit_of_measurement: Unit of measurement override
            native_unit_of_measurement: Native unit of measurement override
            icon: Icon override
            entity_category: Entity category override
        """
        self.instance_id = instance_id
        self.state: Union[str, int, float] = "unavailable"
        self.attributes: Dict[str, Any] = {}

        # Store metadata overrides
        self._unique_id = unique_id
        self._name = name
        self._device_class = device_class
        self._state_class = state_class
        self._unit_of_measurement = unit_of_measurement
        self._native_unit_of_measurement = native_unit_of_measurement
        self._icon = icon
        self._entity_category = entity_category
        self._metadata: Optional[SensorMetadata] = None

    @classmethod
    def get_sensor_class(cls, config_name: str) -> Optional[Type["BaseSensor"]]:
        """Get a sensor class by its config name."""
        return cls._registry.get(config_name)

    @classmethod
    @abstractmethod
    async def discover_sensors(
        cls, config: Optional[Dict[str, Any]] = None
    ) -> list["BaseSensor"]:
        """Discover available sensors of this type.

        Args:
            config: Optional sensor-specific configuration

        Returns:
            List of sensor instances found on the system
        """
        pass

    @abstractmethod
    async def update(self) -> None:
        """Update the sensor state and attributes."""
        pass

    def get_metadata(self) -> SensorMetadata:
        """Get sensor metadata. Can be overridden for dynamic metadata."""
        # Build default metadata
        unique_suffix = f"_{self.instance_id}" if self.instance_id else ""
        return SensorMetadata(
            unique_id=self._unique_id or f"{self.config_name}{unique_suffix}",
            name=self._name or self._get_default_name(),
            config_name=self.config_name,
            device_class=self._device_class,
            state_class=self._state_class,
            unit_of_measurement=self._unit_of_measurement,
            icon=self._icon,
            entity_category=self._entity_category,
            native_unit_of_measurement=self._native_unit_of_measurement,
        )

    def _get_default_name(self) -> str:
        """Get default sensor name."""
        # Convert config_name to title case
        name = self.config_name.replace("_", " ").title()
        if self.instance_id:
            name = f"{name} ({self.instance_id})"
        return name

    def register_payload(self) -> dict:
        """Generate the payload to register the sensor."""
        metadata = self.get_metadata()
        data = {
            "attributes": self.attributes,
            "device_class": metadata.device_class,
            "icon": metadata.icon,
            "name": metadata.name,
            "state": self.state,
            "type": self.sensor_type,
            "unique_id": metadata.unique_id,
            "unit_of_measurement": metadata.unit_of_measurement
            or metadata.native_unit_of_measurement,
            "state_class": metadata.state_class,
            "entity_category": metadata.entity_category,
        }
        return {k: v for k, v in data.items() if v}

    def update_payload(self) -> dict:
        """Generate the payload to update the sensor."""
        metadata = self.get_metadata()
        return {
            "attributes": self.attributes,
            "icon": metadata.icon,
            "state": self.state,
            "type": self.sensor_type,
            "unique_id": metadata.unique_id,
        }
