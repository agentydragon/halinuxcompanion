"""Network hardware class implementation."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import psutil

from ..hardware_base import HardwareClass, HardwarePiece, HardwareProvider, PerPieceUpdateMixin
from ..hardware_config import NetworkConfig, NETWORK_SENSORS

logger = logging.getLogger(__name__)


@dataclass
class NetworkData:
    """Network interface data."""
    status: bool
    tx_bytes: int
    rx_bytes: int
    ipv4_address: Optional[str]
    ipv6_address: Optional[str]


class NetworkInterfacePiece(HardwarePiece[NetworkData]):
    """Represents a single network interface."""
    
    async def _fetch_sensor_data(self) -> Optional[NetworkData]:
        """Fetch fresh sensor data for this network interface."""
        # Get interface statistics
        stats = psutil.net_if_stats().get(self.hardware_id)
        io_counters = psutil.net_io_counters(pernic=True).get(self.hardware_id)
        addrs = psutil.net_if_addrs().get(self.hardware_id, [])
        
        if not stats or not io_counters:
            return None
        
        # Extract addresses and sort deterministically
        ipv4_addresses = sorted(addr.address for addr in addrs if addr.family == 2)  # AF_INET
        ipv6_addresses = sorted(addr.address for addr in addrs if addr.family == 10)  # AF_INET6
        
        return NetworkData(
            status=stats.isup,
            tx_bytes=io_counters.bytes_sent,
            rx_bytes=io_counters.bytes_recv,
            ipv4_address=", ".join(ipv4_addresses) if ipv4_addresses else None,
            ipv6_address=", ".join(ipv6_addresses) if ipv6_addresses else None,
        )
    
    def get_available_sensors(self) -> set[str]:
        """Get set of available sensor types for this interface."""
        return set(NETWORK_SENSORS.keys())
    
    def extract_sensor_value(self, data: NetworkData, sensor_type: str) -> Any:
        """Extract a specific sensor value from network data."""
        # Direct mapping - field names match sensor types
        mapping = {
            "status": data.status,
            "tx_bytes": data.tx_bytes,
            "rx_bytes": data.rx_bytes,
            "ipv4_address": data.ipv4_address,
            "ipv6_address": data.ipv6_address,
        }
        return mapping.get(sensor_type)


class NetworkProvider(HardwareProvider):
    """Network hardware provider."""
    
    def __init__(self, interfaces: List[str]):
        self._configured_interfaces = interfaces
    
    async def discover_hardware(self) -> List[HardwarePiece]:
        """Discover configured network interfaces that exist on the system."""
        available_interfaces = set(psutil.net_if_stats().keys())
        configured = set(self._configured_interfaces)
        
        # Log warnings for configured but non-existent interfaces
        if missing := configured - available_interfaces:
            logger.warning(f"Configured network interfaces not found on system: {', '.join(sorted(missing))}")
        
        existing_interfaces = configured & available_interfaces
        return [NetworkInterfacePiece(iface) for iface in existing_interfaces]


class NetworkHardwareClass(PerPieceUpdateMixin, HardwareClass):
    """Network hardware class."""
    
    hardware_name = "network"
    sensor_definitions = NETWORK_SENSORS
    
    def __init__(self, config: NetworkConfig):
        super().__init__(config)
        self.config: NetworkConfig = config  # Type hint for IDE
    
    async def get_provider(self) -> HardwareProvider:
        """Get the hardware provider."""
        if not self._provider:
            self._provider = NetworkProvider(self.config.interfaces)
        
        return self._provider
    
    def get_enabled_sensors(self, available_sensors: set[str]) -> set[str]:
        enabled = set()
        
        if self.config.show_status:
            enabled |= {"status"}
        
        if self.config.show_counters:
            enabled |= {"tx_bytes", "rx_bytes"}
        
        if self.config.show_ip_addresses:
            enabled |= {"ipv4_address", "ipv6_address"}
        
        return enabled & available_sensors