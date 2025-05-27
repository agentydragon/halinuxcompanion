"""Bluetooth hardware class implementation."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

from ..hardware_base import HardwareSensor, HardwarePiece, HardwareProvider, PerPieceUpdateMixin, StandardHardwareClass
from ..hardware_config import BluetoothConfig, SensorInfo

logger = logging.getLogger(__name__)


@dataclass
class BluetoothData:
    """Bluetooth device data."""
    visible: bool
    connected: bool
    device_name: str
    device_address: str
    battery_level: Optional[int] = None  # percentage (0-100)
    volume: Optional[int] = None  # percentage (0-100)
    playback_state: str = "unknown"


class BluetoothPiece(HardwarePiece):
    """Represents a Bluetooth device."""
    
    def __init__(self, hardware_id: str, device_address: str, device_name: str):
        super().__init__(hardware_id)
        self.device_address = device_address
        self.device_name = device_name
        
        # These will be set by the hardware class when creating sensors
        self.battery_sensor: Optional[HardwareSensor] = None
        self.connected_sensor: Optional[HardwareSensor] = None
        self.visible_sensor: Optional[HardwareSensor] = None
        self.volume_sensor: Optional[HardwareSensor] = None
        self.playback_state_sensor: Optional[HardwareSensor] = None
    
    async def update(self) -> None:
        """Update all sensors for this Bluetooth device."""
        data = await self._fetch_sensor_data()
        
        # Common attributes for all sensors
        attributes = {
            "device_name": data.device_name,
            "device_address": data.device_address,
        }
        
        # Update all sensors that exist
        for sensor, value in [
            (self.visible_sensor, data.visible),
            (self.connected_sensor, data.connected),
            (self.battery_sensor, data.battery_level),
            (self.volume_sensor, data.volume),
            (self.playback_state_sensor, data.playback_state),
        ]:
            if sensor:
                sensor.state = value
                sensor.attributes = attributes
    
    def get_sensors(self) -> List[HardwareSensor]:
        """Get all sensors for this device."""
        return list(filter(None, [
            self.battery_sensor,
            self.connected_sensor,
            self.visible_sensor,
            self.volume_sensor,
            self.playback_state_sensor,
        ]))
    
    async def _fetch_sensor_data(self) -> Optional[BluetoothData]:
        """Fetch fresh sensor data for this Bluetooth device."""
        # Get device info via D-Bus
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        path, interfaces = await self._find_device(bus)
        
        if path and interfaces:
            # Device is visible
            # Get device properties
            device_props = interfaces.get("org.bluez.Device1", {})
            
            # Connection status
            connected = device_props.get("Connected")
            connected_bool = connected.value if isinstance(connected, Variant) else bool(connected) if connected is not None else False
            
            # Battery level - use the working pattern
            battery_level = await self._read_battery(bus, path, interfaces)
            
            # Try to get volume via PulseAudio/PipeWire
            volume = await self._get_volume()
            
            # Try to get playback state via MPRIS2
            playback_state = await self._get_playback_state()
            
            return BluetoothData(
                visible=True,
                connected=connected_bool,
                device_name=self.device_name,
                device_address=self.device_address,
                battery_level=battery_level,
                volume=volume,
                playback_state=playback_state
            )
        else:
            # Device not visible
            return BluetoothData(
                visible=False,
                connected=False,
                device_name=self.device_name,
                device_address=self.device_address
            )
    
    
    async def _find_device(self, bus: MessageBus) -> Tuple[Optional[str], Optional[Dict]]:
        """Find device by MAC address. Returns (path, interfaces) or (None, None)."""
        root = await bus.introspect("org.bluez", "/")
        om = bus.get_proxy_object("org.bluez", "/", root)
        mgr = om.get_interface("org.freedesktop.DBus.ObjectManager")
        
        objs = await mgr.call_get_managed_objects()
        target_mac = self.device_address.upper()
        
        for path, ifaces in objs.items():
            dev = ifaces.get("org.bluez.Device1")
            if dev:
                addr = dev.get("Address")
                if addr and (addr.value if isinstance(addr, Variant) else addr).upper() == target_mac:
                    return path, ifaces
        
        return None, None
    
    async def _read_battery(self, bus: MessageBus, path: str, interfaces: Dict) -> Optional[int]:
        """Read battery level using the working pattern."""
        # Prefer the dedicated Battery1 interface if present
        if "org.bluez.Battery1" in interfaces:
            node = await bus.introspect("org.bluez", path)
            batt = bus.get_proxy_object("org.bluez", path, node).get_interface("org.bluez.Battery1")
            pct = await batt.get_percentage()
            return pct
        
        # Fallback to BatteryPercentage property on Device1
        battery_pct = interfaces["org.bluez.Device1"].get("BatteryPercentage")
        if battery_pct is not None:
            return battery_pct.value if isinstance(battery_pct, Variant) else battery_pct
        
        return None
    
    async def _get_volume(self) -> Optional[int]:
        """Get volume level via PulseAudio."""
        try:
            import pulsectl
        except ImportError:
            return None
        
        with pulsectl.Pulse("halinuxcompanion") as pulse:
            # Find the device in PulseAudio
            addr_underscore = self.device_address.replace(":", "_")
            
            for sink in pulse.sink_list():
                if addr_underscore in sink.name:
                    # Convert volume to percentage
                    return int(pulse.volume_get_all_chans(sink) * 100)
            
            for source in pulse.source_list():
                if addr_underscore in source.name:
                    return int(pulse.volume_get_all_chans(source) * 100)
        
        return None
    
    async def _get_playback_state(self) -> str:
        """Get playback state via MPRIS2."""
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        
        # Get list of names
        introspection = await bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
        proxy = bus.get_proxy_object("org.freedesktop.DBus", "/org/freedesktop/DBus", introspection)
        dbus_interface = proxy.get_interface("org.freedesktop.DBus")
        
        names = await dbus_interface.call_list_names()
        
        # Look for MPRIS2 players
        for service in names:
            if service.startswith("org.mpris.MediaPlayer2."):
                try:
                    player_introspection = await bus.introspect(service, "/org/mpris/MediaPlayer2")
                    player_proxy = bus.get_proxy_object(service, "/org/mpris/MediaPlayer2", player_introspection)
                    props = player_proxy.get_interface("org.freedesktop.DBus.Properties")
                    
                    playback_status = await props.call_get("org.mpris.MediaPlayer2.Player", "PlaybackStatus")
                    if playback_status:
                        return playback_status.lower()  # playing, paused, stopped
                except Exception:
                    continue
        
        return "unknown"


class BluetoothProvider(HardwareProvider):
    """Bluetooth hardware provider."""
    
    def __init__(self, whitelisted_devices: List[str]):
        self.whitelisted_devices = set(whitelisted_devices)
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover whitelisted Bluetooth devices."""
        if not self.whitelisted_devices:
            logger.debug("No Bluetooth devices whitelisted")
            return []
        
        pieces = []
        
        # Use D-Bus to find devices instead of pybluez
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        root = await bus.introspect("org.bluez", "/")
        om = bus.get_proxy_object("org.bluez", "/", root)
        mgr = om.get_interface("org.freedesktop.DBus.ObjectManager")
        
        objs = await mgr.call_get_managed_objects()
        
        for path, ifaces in objs.items():
            dev = ifaces.get("org.bluez.Device1")
            if dev:
                addr_variant = dev.get("Address")
                name_variant = dev.get("Name") or dev.get("Alias")
                
                if addr_variant:
                    addr = addr_variant.value if isinstance(addr_variant, Variant) else addr_variant
                    name = name_variant.value if isinstance(name_variant, Variant) else name_variant if name_variant else addr
                    
                    if addr in self.whitelisted_devices:
                        hardware_id = addr.replace(":", "")
                        pieces.append(BluetoothPiece(hardware_id, addr, name))
                        logger.debug(f"Discovered Bluetooth device: {name} ({addr})")
        
        if pieces:
            logger.debug(f"Discovered {len(pieces)} whitelisted Bluetooth devices")
        else:
            logger.debug("No whitelisted Bluetooth devices found")
        
        return pieces


class BluetoothHardwareClass(PerPieceUpdateMixin, StandardHardwareClass):
    """Bluetooth hardware class."""
    
    hardware_name = "bluetooth"
    sensor_definitions = {
        "battery_level": SensorInfo(
            name="Battery Level",
            unit="%",
            device_class="battery",
            state_class="measurement",
            icon="mdi:battery-bluetooth"
        ),
        "connected": SensorInfo(
            type="binary_sensor",
            name="Connected",
            device_class="connectivity",
            icon="mdi:bluetooth-connect"
        ),
        "visible": SensorInfo(
            type="binary_sensor",
            name="Visible",
            device_class="presence",
            icon="mdi:bluetooth-audio"
        ),
        "volume": SensorInfo(
            name="Volume",
            unit="%",
            state_class="measurement",
            icon="mdi:volume-high"
        ),
        "playback_state": SensorInfo(
            name="Playback State",
            icon="mdi:play-pause"
        )
    }
    
    def __init__(self, config: BluetoothConfig):
        super().__init__(config)
        self.config: BluetoothConfig = config
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = BluetoothProvider(self.config.devices)
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        # Enable all available sensors
        return available_sensors
    
    async def discover_sensors(self) -> List[HardwareSensor]:
        """Discover sensors and assign them to pieces."""
        if not self.config.enabled:
            return []
        
        provider = await self.get_provider()
        hardware_pieces = await provider.discover_hardware()
        
        # Store hardware pieces for update_all_sensors
        self._hardware_pieces = hardware_pieces
        
        all_sensors = []
        
        for piece in hardware_pieces:
            # Create sensors for this piece
            piece.battery_sensor = HardwareSensor(
                hardware_class=self.hardware_name,
                hardware_id=piece.hardware_id,
                sensor_type_name="battery_level",
                sensor_info=SensorInfo(
                    name="Battery Level",
                    unit="%",
                    device_class="battery",
                    state_class="measurement",
                    icon="mdi:battery-bluetooth"
                ),
                hardware_piece=piece,
            )
            
            piece.connected_sensor = HardwareSensor(
                hardware_class=self.hardware_name,
                hardware_id=piece.hardware_id,
                sensor_type_name="connected",
                sensor_info=SensorInfo(
                    type="binary_sensor",
                    name="Connected",
                    device_class="connectivity",
                    icon="mdi:bluetooth-connect"
                ),
                hardware_piece=piece,
            )
            
            piece.visible_sensor = HardwareSensor(
                hardware_class=self.hardware_name,
                hardware_id=piece.hardware_id,
                sensor_type_name="visible",
                sensor_info=SensorInfo(
                    type="binary_sensor",
                    name="Visible",
                    device_class="presence",
                    icon="mdi:bluetooth-audio"
                ),
                hardware_piece=piece,
            )
            
            piece.volume_sensor = HardwareSensor(
                hardware_class=self.hardware_name,
                hardware_id=piece.hardware_id,
                sensor_type_name="volume",
                sensor_info=SensorInfo(
                    name="Volume",
                    unit="%",
                    state_class="measurement",
                    icon="mdi:volume-high"
                ),
                hardware_piece=piece,
            )
            
            piece.playback_state_sensor = HardwareSensor(
                hardware_class=self.hardware_name,
                hardware_id=piece.hardware_id,
                sensor_type_name="playback_state",
                sensor_info=SensorInfo(
                    name="Playback State",
                    icon="mdi:play-pause"
                ),
                hardware_piece=piece,
            )
            
            # Get all sensors from the piece
            all_sensors.extend(piece.get_sensors())
        
        return all_sensors