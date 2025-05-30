"""Sensor implementations for halinuxcompanion."""

# List of all available sensor config names
__all__ = [
    # Battery sensors
    "battery_psutil",
    "battery_psutil_time_to_empty",
    "battery_upower",
    "battery_upower_charge_cycles",
    "battery_upower_energy",
    "battery_upower_energy_full",
    "battery_upower_health",
    "battery_upower_power",
    "battery_upower_temperature",
    "battery_upower_time_to_empty",
    "battery_upower_time_to_full",
    "battery_upower_voltage",
    # Other sensors
    "bluetooth_device",
    "camera_state",
    "cpu",
    "lid_state",
    "memory",
    "network_interface",
    "network_interface_status",
    "status",
    "temperature",
    "uptime",
]
