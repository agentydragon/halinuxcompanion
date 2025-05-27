"""Base classes for module implementation that can create multiple sensors."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Type

from .sensor_base import BaseSensor

logger = logging.getLogger(__name__)


@dataclass
class ModuleDevice:
    """Represents a logical device that groups related sensors."""

    device_id: str  # Unique ID for this device instance
    device_name: str  # Human-readable name
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    sw_version: Optional[str] = None
    hw_version: Optional[str] = None


class BaseModule(ABC):
    """Abstract base class for modules that can create multiple sensors.

    A module represents a logical grouping of functionality (e.g., battery monitoring,
    bluetooth device tracking) that may create multiple sensor entities.
    """

    # Module-level configuration
    module_name: ClassVar[str]  # e.g., "battery", "bluetooth_devices"

    # Registry of all module classes
    _registry: ClassVar[Dict[str, Type["BaseModule"]]] = {}

    def __init__(self):
        """Initialize module."""
        self.sensors: List[BaseSensor] = []
        self.devices: Dict[str, ModuleDevice] = {}

    @classmethod
    def register(cls, module_name: str):
        """Decorator to register a module class.
        
        Usage:
            @BaseModule.register("battery")
            class BatteryModule(BaseModule):
                ...
        """
        def decorator(module_class: Type["BaseModule"]) -> Type["BaseModule"]:
            module_class.module_name = module_name
            cls._registry[module_name] = module_class
            return module_class
        return decorator

    @classmethod
    @abstractmethod
    async def discover(cls, config: Optional[Dict[str, Any]] = None) -> Optional["BaseModule"]:
        """Discover if this module can run on the system and create instance if so.

        Args:
            config: Module-specific configuration

        Returns:
            Module instance with discovered sensors, or None if module cannot run
        """
        pass

    def get_sensors(self) -> List[BaseSensor]:
        """Get all sensors created by this module."""
        return self.sensors

    def get_devices(self) -> Dict[str, ModuleDevice]:
        """Get all logical devices managed by this module."""
        return self.devices
