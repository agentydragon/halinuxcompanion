"""Base classes for hardware class → hardware piece → sensor hierarchy."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Type, TypeVar, Generic

from .sensor_base import SensorMetadata
from .hardware_config import HardwareClassConfig, SensorInfo

logger = logging.getLogger(__name__)

# Type variable for sensor data
TSensorData = TypeVar('TSensorData')


class HardwareSensor:
    """A sensor that belongs to a specific hardware piece."""
    
    def __init__(
        self,
        hardware_class: str,
        hardware_id: str,
        sensor_type_name: str,
        sensor_info: SensorInfo,
        hardware_piece: Optional["HardwarePiece"] = None,
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
        
        # Sensor type for HA (sensor or binary_sensor)
        self.sensor_type = sensor_info.type
    
    def get_metadata(self) -> SensorMetadata:
        """Get sensor metadata."""
        # Use device name if available (e.g., for bluetooth devices)
        display_name = self.hardware_id
        if hasattr(self._hardware_piece, 'device_name'):
            display_name = self._hardware_piece.device_name
        
        # Format: "Hardware ID - Sensor Type"
        name = f"{display_name} - {self.sensor_info.name}"
        
        return SensorMetadata(
            unique_id=f"{self.hardware_class}_{self.hardware_id}_{self.sensor_type_name}",
            name=name,
            config_name="",  # Not used for hardware sensors
            device_class=self.sensor_info.device_class,
            state_class=self.sensor_info.state_class,
            unit_of_measurement=self.sensor_info.unit,
            icon=self.sensor_info.icon,
            native_unit_of_measurement=self.sensor_info.unit,
        )
    


class HardwarePiece:
    """Represents a specific piece of hardware (e.g., a specific battery, network interface).
    
    This is an optional helper class that hardware implementations may use.
    It provides no required interface - implementations define their own.
    """
    
    def __init__(self, hardware_id: str):
        """Initialize a hardware piece.
        
        Args:
            hardware_id: Unique identifier for this hardware piece
        """
        self.hardware_id = hardware_id


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
    
    hardware_name: str  # Must be set by subclasses
    sensor_definitions: Dict[str, SensorInfo]  # Must be set by subclasses
    
    def __init__(self, config: HardwareClassConfig):
        """Initialize hardware class with configuration.
        
        Args:
            config: Configuration for this hardware class
        """
        self.config = config
        self._provider: Optional[HardwareProvider] = None
        self._hardware_pieces: List[HardwarePiece] = []
    
    
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


class StandardHardwareClass(HardwareClass):
    """Standard hardware class implementation using pieces pattern.
    
    This provides a common implementation pattern where:
    1. Hardware is discovered as "pieces" (e.g., each battery, network interface)
    2. Each piece knows what sensors it can provide
    3. Sensors are created for each piece
    4. The update pattern can be:
       - Use PerPieceUpdateMixin: each piece has update() method
       - Override update_all_sensors(): custom bulk update logic
    
    The flow is:
    1. discover_sensors() calls get_provider() to get a HardwareProvider
    2. HardwareProvider.discover_hardware() returns hardware pieces
    3. For each piece, we ask what sensors it supports
    4. We create HardwareSensor instances for each enabled sensor type
    5. During updates, the implementation decides how to populate sensor.state
    
    Example piece with update() method:
        class BatteryPiece(HardwarePiece):
            async def update(self):
                data = await fetch_battery_data()
                for sensor in self.sensors:
                    if sensor.sensor_type_name == "charge_level":
                        sensor.state = data.charge_level
    
    Subclasses need to implement:
    - get_provider(): Return a HardwareProvider instance
    - get_enabled_sensors(): Filter which sensors to create (optional)
    - update_all_sensors(): How to update sensors (or use PerPieceUpdateMixin)
    """
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider. Subclasses must override."""
        raise NotImplementedError
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        """Filter which sensors to enable. Default: all available."""
        return available_sensors
    
    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover all sensors using the standard pattern."""
        if not self.config.enabled:
            return []
        
        provider = await self.get_provider()
        hardware_pieces = await provider.discover_hardware()
        
        # Store hardware pieces for update_all_sensors/PerPieceUpdateMixin
        self._hardware_pieces = hardware_pieces
        
        sensors = []
        for hardware_piece in hardware_pieces:
            # Get available sensors for this piece
            available = hardware_piece.get_available_sensors()
            
            # Let the hardware class decide which sensors to enable
            enabled_sensors = self.get_enabled_sensors(available)
            
            # Create sensor instances
            for sensor_type in enabled_sensors:
                if sensor_type not in self.sensor_definitions:
                    logger.warning(f"Unknown sensor type {sensor_type} for {self.hardware_name}")
                    continue
                
                sensor_info = self.sensor_definitions[sensor_type]
                sensor = HardwareSensor(
                    hardware_class=self.hardware_name,
                    hardware_id=hardware_piece.hardware_id,
                    sensor_type_name=sensor_type,
                    sensor_info=sensor_info,
                    hardware_piece=hardware_piece,
                )
                
                sensors.append(sensor)
                
                # Let the piece store a reference if it wants
                # (e.g., for pieces that push data to sensors)
                if hasattr(hardware_piece, 'sensors'):
                    hardware_piece.sensors.append(sensor)
        
        return sensors


# Registry for hardware classes
HARDWARE_CLASSES: Dict[str, Type[HardwareClass]] = {}