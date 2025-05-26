"""Base classes for sensor implementation with proper inheritance and discovery."""

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Optional, Set, Type, Union

logger = logging.getLogger(__name__)


class SensorMetadata:
    """Metadata for a sensor instance."""
    
    def __init__(
        self,
        unique_id: str,
        name: str,
        config_name: str,
        device_class: Optional[str] = None,
        state_class: Optional[str] = None,
        unit_of_measurement: Optional[str] = None,
        icon: Optional[str] = None,
        entity_category: Optional[str] = None,
    ):
        self.unique_id = unique_id
        self.name = name
        self.config_name = config_name
        self.device_class = device_class
        self.state_class = state_class
        self.unit_of_measurement = unit_of_measurement
        self.icon = icon
        self.entity_category = entity_category


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
    
    def __init__(self, instance_id: str = ""):
        """Initialize a sensor instance.
        
        Args:
            instance_id: Unique identifier for this instance (e.g., "BAT0" for battery)
        """
        self.instance_id = instance_id
        self.state: Union[str, int, float] = "unavailable"
        self.attributes: Dict[str, Any] = {}
        self._metadata: Optional[SensorMetadata] = None
        
    def __init_subclass__(cls, **kwargs):
        """Register sensor subclasses automatically."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'config_name'):
            cls._registry[cls.config_name] = cls
            
    @classmethod
    def get_sensor_class(cls, config_name: str) -> Optional[Type["BaseSensor"]]:
        """Get a sensor class by its config name."""
        return cls._registry.get(config_name)
    
    @classmethod
    def get_all_sensor_classes(cls) -> Dict[str, Type["BaseSensor"]]:
        """Get all registered sensor classes."""
        return cls._registry.copy()
    
    @classmethod
    @abstractmethod
    async def discover_sensors(cls) -> List["BaseSensor"]:
        """Discover available sensors of this type.
        
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
        if self._metadata is None:
            # Build default metadata
            unique_suffix = f"_{self.instance_id}" if self.instance_id else ""
            self._metadata = SensorMetadata(
                unique_id=f"{self.config_name}{unique_suffix}",
                name=self._get_default_name(),
                config_name=self.config_name,
            )
        return self._metadata
    
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
            "unit_of_measurement": metadata.unit_of_measurement,
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


class DiscoverySensorManager:
    """Manages sensor discovery and lifecycle."""
    
    def __init__(self):
        self.sensors: Dict[str, BaseSensor] = {}  # unique_id -> sensor
        self.enabled_sensor_types: Set[str] = set()
        
    async def discover_all(self, enabled_sensors: List[str]) -> List[BaseSensor]:
        """Discover all enabled sensors.
        
        Args:
            enabled_sensors: List of sensor config names to enable
            
        Returns:
            List of discovered sensor instances
        """
        self.enabled_sensor_types = set(enabled_sensors)
        discovered = []
        
        for config_name in enabled_sensors:
            sensor_class = BaseSensor.get_sensor_class(config_name)
            if sensor_class is None:
                logger.warning(f"Unknown sensor type: {config_name}")
                continue
                
            try:
                instances = await sensor_class.discover_sensors()
                for sensor in instances:
                    unique_id = sensor.get_metadata().unique_id
                    self.sensors[unique_id] = sensor
                    discovered.append(sensor)
                    
                if instances:
                    logger.info(f"Discovered {len(instances)} {config_name} sensor(s)")
                else:
                    logger.info(f"No {config_name} sensors found")
                    
            except Exception as e:
                logger.error(f"Error discovering {config_name} sensors: {e}")
                
        return discovered
    
    async def update_all(self) -> None:
        """Update all discovered sensors."""
        for sensor in self.sensors.values():
            try:
                await sensor.update()
            except Exception as e:
                logger.error(f"Error updating sensor {sensor.get_metadata().unique_id}: {e}")
    
    def get_sensor(self, unique_id: str) -> Optional[BaseSensor]:
        """Get a sensor by its unique ID."""
        return self.sensors.get(unique_id)
    
    def get_all_sensors(self) -> List[BaseSensor]:
        """Get all discovered sensors."""
        return list(self.sensors.values())
    
    async def check_for_changes(self) -> tuple[List[BaseSensor], List[str]]:
        """Check for added or removed sensors.
        
        Returns:
            Tuple of (added_sensors, removed_unique_ids)
        """
        current_sensors = {}
        added = []
        
        # Rediscover all enabled sensor types
        for config_name in self.enabled_sensor_types:
            sensor_class = BaseSensor.get_sensor_class(config_name)
            if sensor_class is None:
                continue
                
            try:
                instances = await sensor_class.discover_sensors()
                for sensor in instances:
                    unique_id = sensor.get_metadata().unique_id
                    current_sensors[unique_id] = sensor
                    
                    if unique_id not in self.sensors:
                        added.append(sensor)
                        
            except Exception as e:
                logger.error(f"Error rediscovering {config_name} sensors: {e}")
        
        # Find removed sensors
        removed = []
        for unique_id in list(self.sensors.keys()):
            if unique_id not in current_sensors:
                removed.append(unique_id)
                del self.sensors[unique_id]
        
        # Add new sensors
        for sensor in added:
            unique_id = sensor.get_metadata().unique_id
            self.sensors[unique_id] = sensor
            
        return added, removed