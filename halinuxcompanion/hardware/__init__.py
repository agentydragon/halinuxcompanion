"""Hardware class implementations."""

from .battery_hardware import BatteryHardwareClass
from .bluetooth import BluetoothHardwareClass
from .camera import CameraHardwareClass
from .cpu import CPUHardwareClass
from .lid import LidHardwareClass
from .memory import MemoryHardwareClass
from .network import NetworkHardwareClass
from .temperature import TemperatureHardwareClass
from .uptime import UptimeHardwareClass

__all__ = [
    "BatteryHardwareClass",
    "BluetoothHardwareClass",
    "CPUHardwareClass",
    "CameraHardwareClass",
    "LidHardwareClass",
    "MemoryHardwareClass",
    "NetworkHardwareClass",
    "TemperatureHardwareClass",
    "UptimeHardwareClass",
]
