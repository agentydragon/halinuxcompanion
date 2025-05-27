"""Hierarchical hardware configuration models."""

from typing import Dict, List, Literal, Optional, Any
from pydantic import BaseModel, Field


class SensorInfo(BaseModel):
    """Definition of a sensor type."""
    type: Literal["sensor", "binary_sensor"] = "sensor"
    name: str
    unit: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    icon: Optional[str] = None


class HardwareClassConfig(BaseModel):
    """Base configuration for a hardware class."""
    enabled: bool = False


class BatteryConfig(HardwareClassConfig):
    """Configuration for battery hardware class."""
    implementation: Literal["psutil", "upower"] = "psutil"
    # All sensors enabled by default
    # TODO: Add support for multiple batteries (battery_ids)


class NetworkConfig(HardwareClassConfig):
    """Configuration for network hardware class."""
    interfaces: List[str] = Field(
        default_factory=list,
        description="List of network interfaces to monitor (e.g., ['eth0', 'wlan0'])"
    )
    # Feature flags that control groups of sensors
    show_status: bool = True  # status binary sensor
    show_counters: bool = True  # tx_bytes, rx_bytes sensors
    show_ip_addresses: bool = False  # ipv4_address, ipv6_address sensors


class CPUConfig(HardwareClassConfig):
    """Configuration for CPU hardware class."""
    # Always shows usage_percent and frequency


class MemoryConfig(HardwareClassConfig):
    """Configuration for memory hardware class."""
    # Always shows usage_percent, used_mb, available_mb
    # TODO: Expose more precise units - psutil returns bytes, we could expose as kB/MB/GB with proper unit


class CameraConfig(HardwareClassConfig):
    """Configuration for camera hardware class."""
    # Creates binary_sensor per camera for in_use status
    # TODO: Add support for selecting specific cameras (camera_ids)


class LidConfig(HardwareClassConfig):
    """Configuration for lid hardware class."""
    # Single binary_sensor for lid open/closed


class BluetoothConfig(HardwareClassConfig):
    """Configuration for bluetooth hardware class."""
    devices: List[str] = Field(
        default_factory=list,
        description="List of Bluetooth device MAC addresses to monitor"
    )
    # Creates binary_sensor per device for connected status


class StatusConfig(HardwareClassConfig):
    """Configuration for system status hardware class."""
    # Single sensor showing overall system status


class UptimeConfig(HardwareClassConfig):
    """Configuration for uptime hardware class."""
    # Single sensor showing system uptime


class TemperatureConfig(HardwareClassConfig):
    """Configuration for temperature hardware class."""
    # TODO: Add sensor filtering/selection - for now expose all available temperature sensors


class HardwareConfig(BaseModel):
    """Root hardware configuration containing all hardware classes."""
    battery: Optional[BatteryConfig] = None
    network: Optional[NetworkConfig] = None
    cpu: Optional[CPUConfig] = None
    memory: Optional[MemoryConfig] = None
    camera: Optional[CameraConfig] = None
    lid: Optional[LidConfig] = None
    bluetooth: Optional[BluetoothConfig] = None
    status: Optional[StatusConfig] = None
    uptime: Optional[UptimeConfig] = None
    temperature: Optional[TemperatureConfig] = None


# Sensor definitions for each hardware class
BATTERY_SENSORS: Dict[str, SensorInfo] = {
    "charge_level": SensorInfo(
        name="Battery Level", 
        unit="%", 
        device_class="battery",
        state_class="measurement"
    ),
    "charging_state": SensorInfo(
        name="Battery State",
        icon="mdi:battery"
    ),
    "time_to_empty": SensorInfo(
        name="Time to Empty", 
        unit="min", 
        device_class="duration",
        state_class="measurement"
    ),
    "time_to_full": SensorInfo(
        name="Time to Full", 
        unit="min", 
        device_class="duration",
        state_class="measurement"
    ),
    "temperature": SensorInfo(
        name="Battery Temperature", 
        unit="°C", 
        device_class="temperature",
        state_class="measurement"
    ),
    "voltage": SensorInfo(
        name="Battery Voltage", 
        unit="V", 
        device_class="voltage",
        state_class="measurement"
    ),
    "charge_rate": SensorInfo(
        name="Charge Rate", 
        unit="W", 
        device_class="power",
        state_class="measurement"
    ),
    "discharge_rate": SensorInfo(
        name="Discharge Rate", 
        unit="W", 
        device_class="power",
        state_class="measurement"
    ),
    "health": SensorInfo(
        name="Battery Health", 
        unit="%",
        state_class="measurement"
    ),
    "charge_cycles": SensorInfo(
        name="Charge Cycles",
        state_class="total_increasing"
    ),
    "energy": SensorInfo(
        name="Battery Energy", 
        unit="Wh", 
        device_class="energy",
        state_class="measurement"
    ),
    "energy_full": SensorInfo(
        name="Battery Energy Full", 
        unit="Wh", 
        device_class="energy",
        state_class="measurement"
    ),
}

NETWORK_SENSORS: Dict[str, SensorInfo] = {
    "status": SensorInfo(
        type="binary_sensor",
        name="Status",
        device_class="connectivity"
    ),
    "tx_bytes": SensorInfo(
        name="TX Bytes",
        unit="B",
        device_class="data_size",
        state_class="total_increasing"
    ),
    "rx_bytes": SensorInfo(
        name="RX Bytes", 
        unit="B",
        device_class="data_size",
        state_class="total_increasing"
    ),
    "ipv4_address": SensorInfo(
        name="IPv4 Address",
        icon="mdi:ip-network"
    ),
    "ipv6_address": SensorInfo(
        name="IPv6 Address",
        icon="mdi:ip-network"
    ),
}

CPU_SENSORS: Dict[str, SensorInfo] = {
    "usage_percent": SensorInfo(
        name="CPU Usage", 
        unit="%",
        state_class="measurement"
    ),
    "frequency": SensorInfo(
        name="CPU Frequency", 
        unit="MHz", 
        device_class="frequency",
        state_class="measurement"
    ),
}

MEMORY_SENSORS: Dict[str, SensorInfo] = {
    "usage_percent": SensorInfo(
        name="Memory Usage", 
        unit="%",
        state_class="measurement"
    ),
    "used": SensorInfo(
        name="Memory Used", 
        unit="B", 
        device_class="data_size",
        state_class="measurement"
    ),
    "available": SensorInfo(
        name="Memory Available", 
        unit="B", 
        device_class="data_size",
        state_class="measurement"
    ),
}