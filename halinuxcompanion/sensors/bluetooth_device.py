"""Bluetooth device sensors."""

import asyncio
import logging
from typing import Any, Dict, Optional

from halinuxcompanion.sensor_base import BaseSensor, SensorMetadata

logger = logging.getLogger(__name__)


class BluetoothDeviceSensor(BaseSensor):
    """Base class for Bluetooth device sensors."""

    config_name = "bluetooth_device"

    def __init__(self, device_address: str, device_name: str, sensor_suffix: str):
        """Initialize a Bluetooth device sensor."""
        self.device_address = device_address
        self.device_name = device_name
        self.sensor_suffix = sensor_suffix
        super().__init__()

    @property
    def metadata(self) -> SensorMetadata:
        """Return sensor metadata."""
        # Base metadata - subclasses will override
        return SensorMetadata(
            unique_id=f"bluetooth_{self.device_address.replace(':', '')}_{self.sensor_suffix}",
            name=f"{self.device_name} {self.sensor_suffix.replace('_', ' ').title()}",
            config_name=self.config_name,
        )

    @classmethod
    async def discover_sensors(cls, config: Optional[Dict[str, Any]] = None) -> list["BaseSensor"]:
        """Discover available Bluetooth devices."""
        sensors = []

        if not config:
            logger.debug("No config provided for Bluetooth device sensor")
            return sensors

        whitelisted_devices = config.get("devices", [])

        if not whitelisted_devices:
            logger.debug("No Bluetooth devices whitelisted in config")
            return sensors

        # Try to import bluetooth library
        try:
            import bluetooth
        except ImportError:
            raise ImportError("pybluez not installed, cannot use Bluetooth sensors")

        # Discover devices
        try:
            # Perform device discovery
            nearby_devices = await asyncio.get_event_loop().run_in_executor(
                None, bluetooth.discover_devices, 8, True, True
            )

            for addr, name, device_class in nearby_devices:
                if addr in whitelisted_devices:
                    # Create sensors for each whitelisted device
                    sensors.extend(
                        [
                            BluetoothBatteryLevelSensor(addr, name or addr),
                            BluetoothConnectedSensor(addr, name or addr),
                            BluetoothVisibleSensor(addr, name or addr),
                            BluetoothVolumeSensor(addr, name or addr),
                            BluetoothPlaybackStateSensor(addr, name or addr),
                            BluetoothDebugSensor(addr, name or addr),
                        ]
                    )
                    logger.info(f"Added Bluetooth sensors for device {name} ({addr})")
        except Exception:
            logger.error("Failed to discover Bluetooth devices", exc_info=True)

        return sensors

    async def _get_device_info(self) -> Optional[dict]:
        """Get device info via D-Bus."""
        try:
            import dbus

            bus = dbus.SystemBus()
            manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")

            objects = await asyncio.get_event_loop().run_in_executor(None, manager.GetManagedObjects)

            # Find our device
            for interfaces in objects.values():
                if "org.bluez.Device1" in interfaces:
                    device = interfaces["org.bluez.Device1"]
                    if device.get("Address") == self.device_address:
                        return device

            return None
        except Exception:
            logger.debug(f"Failed to get device info for {self.device_address}", exc_info=True)
            return None


class BluetoothBatteryLevelSensor(BluetoothDeviceSensor):
    """Bluetooth device battery level sensor."""

    def __init__(self, device_address: str, device_name: str):
        """Initialize battery level sensor."""
        super().__init__(device_address, device_name, "battery_level")

    @property
    def metadata(self) -> SensorMetadata:
        """Return sensor metadata."""
        metadata = super().metadata
        metadata.device_class = "battery"
        metadata.state_class = "measurement"
        metadata.unit_of_measurement = "%"
        metadata.icon = "mdi:battery-bluetooth"
        return metadata

    async def get_state(self) -> Any:
        """Get the battery level."""
        device_info = await self._get_device_info()
        # Check if battery level is available
        if device_info and (battery_level := device_info.get("BatteryPercentage")) is not None:
            return int(battery_level)
        return None


class BluetoothConnectedSensor(BluetoothDeviceSensor):
    """Bluetooth device connected status sensor."""

    sensor_type = "binary_sensor"

    def __init__(self, device_address: str, device_name: str):
        """Initialize connected sensor."""
        super().__init__(device_address, device_name, "connected")

    @property
    def metadata(self) -> SensorMetadata:
        """Return sensor metadata."""
        metadata = super().metadata
        metadata.device_class = "connectivity"
        metadata.icon = "mdi:bluetooth-connect"
        return metadata

    async def get_state(self) -> Any:
        """Get the connected status."""
        device_info = await self._get_device_info()
        if device_info:
            return device_info.get("Connected", False)
        return False


class BluetoothVisibleSensor(BluetoothDeviceSensor):
    """Bluetooth device visible status sensor."""

    sensor_type = "binary_sensor"

    def __init__(self, device_address: str, device_name: str):
        """Initialize visible sensor."""
        super().__init__(device_address, device_name, "visible")

    @property
    def metadata(self) -> SensorMetadata:
        """Return sensor metadata."""
        metadata = super().metadata
        metadata.device_class = "presence"
        metadata.icon = "mdi:bluetooth-audio"
        return metadata

    async def get_state(self) -> Any:
        """Get the visible status."""
        # Check if device exists in BlueZ - if it does, it's visible
        device_info = await self._get_device_info()
        return device_info is not None


class BluetoothVolumeSensor(BluetoothDeviceSensor):
    """Bluetooth device volume sensor."""

    def __init__(self, device_address: str, device_name: str):
        """Initialize volume sensor."""
        super().__init__(device_address, device_name, "volume")

    @property
    def metadata(self) -> SensorMetadata:
        """Return sensor metadata."""
        metadata = super().metadata
        metadata.state_class = "measurement"
        metadata.unit_of_measurement = "%"
        metadata.icon = "mdi:volume-high"
        return metadata

    async def get_state(self) -> Any:
        """Get the volume level."""
        # Try to get volume via PulseAudio/PipeWire
        try:
            import pulsectl

            with pulsectl.Pulse("halinuxcompanion") as pulse:
                # Find the device in PulseAudio
                for sink in pulse.sink_list():
                    if self.device_address.replace(":", "_") in sink.name:
                        # Convert volume to percentage
                        return int(pulse.volume_get_all_chans(sink) * 100)

                for source in pulse.source_list():
                    if self.device_address.replace(":", "_") in source.name:
                        return int(pulse.volume_get_all_chans(source) * 100)
        except Exception:
            logger.debug(f"Failed to get volume for {self.device_address}", exc_info=True)

        return None


class BluetoothPlaybackStateSensor(BluetoothDeviceSensor):
    """Bluetooth device playback state sensor."""

    def __init__(self, device_address: str, device_name: str):
        """Initialize playback state sensor."""
        super().__init__(device_address, device_name, "playback_state")

    @property
    def metadata(self) -> SensorMetadata:
        """Return sensor metadata."""
        metadata = super().metadata
        metadata.icon = "mdi:play-pause"
        return metadata

    async def get_state(self) -> Any:
        """Get the playback state."""
        # Try to get media player status via MPRIS2
        try:
            import dbus

            bus = dbus.SessionBus()

            # Look for MPRIS2 players
            for service in bus.list_names():
                if service.startswith("org.mpris.MediaPlayer2."):
                    try:
                        player = bus.get_object(service, "/org/mpris/MediaPlayer2")
                        props = dbus.Interface(player, "org.freedesktop.DBus.Properties")

                        # Check if this player is using our Bluetooth device
                        # This is a heuristic - might need device-specific logic
                        playback_status = props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus")
                        if playback_status:
                            return playback_status.lower()  # playing, paused, stopped
                    except Exception:
                        continue
        except Exception:
            logger.debug(f"Failed to get playback state for {self.device_address}", exc_info=True)

        return "unknown"


class BluetoothDebugSensor(BluetoothDeviceSensor):
    """Bluetooth device debug info sensor."""

    def __init__(self, device_address: str, device_name: str):
        """Initialize debug sensor."""
        super().__init__(device_address, device_name, "debug_info")

    @property
    def metadata(self) -> SensorMetadata:
        """Return sensor metadata."""
        metadata = super().metadata
        metadata.icon = "mdi:bug"
        return metadata

    async def get_state(self) -> Any:
        """Get all available device info as JSON."""
        device_info = await self._get_device_info()
        if device_info:
            # Convert D-Bus types to Python native types
            debug_info = {}
            for key, value in device_info.items():
                try:
                    # Handle various D-Bus types
                    if hasattr(value, "__iter__") and not isinstance(value, str):
                        debug_info[key] = list(value)
                    else:
                        debug_info[key] = str(value)
                except Exception:
                    debug_info[key] = repr(value)

            return debug_info
        return {}
