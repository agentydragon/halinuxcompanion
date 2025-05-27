"""Hardware class implementations."""

from .battery import BatteryHardwareClass
from .network import NetworkHardwareClass
from .cpu import CPUHardwareClass
from .memory import MemoryHardwareClass
from .lid import LidHardwareClass
from .temperature import TemperatureHardwareClass
from .camera import CameraHardwareClass
from .bluetooth import BluetoothHardwareClass
from .uptime import UptimeHardwareClass

__all__ = [
    "BatteryHardwareClass",
    "NetworkHardwareClass",
    "CPUHardwareClass",
    "MemoryHardwareClass",
    "LidHardwareClass",
    "TemperatureHardwareClass",
    "CameraHardwareClass",
    "BluetoothHardwareClass",
    "UptimeHardwareClass",
]