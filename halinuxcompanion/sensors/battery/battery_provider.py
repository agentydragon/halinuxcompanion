"""Battery data provider base classes and interfaces."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BatteryData:
    """Unified battery data structure."""

    # Identity
    battery_id: str
    name: str

    # Basic info
    percent: float
    plugged: bool
    state: str  # "Charging", "Discharging", "Full", "Unknown"

    # Time estimates
    time_to_empty: Optional[int] = None  # seconds
    time_to_full: Optional[int] = None  # seconds

    # Power/energy metrics
    charge_rate: Optional[float] = None  # W
    discharge_rate: Optional[float] = None  # W
    energy: Optional[float] = None  # Wh
    energy_full: Optional[float] = None  # Wh
    energy_full_design: Optional[float] = None  # Wh

    # Battery health
    capacity: Optional[float] = None  # percentage (0-100)
    charge_cycles: Optional[int] = None

    # Physical properties
    voltage: Optional[float] = None  # V
    temperature: Optional[float] = None  # °C

    # Device info
    technology: Optional[str] = None
    model: Optional[str] = None
    vendor: Optional[str] = None
    serial: Optional[str] = None

    # Status flags
    warning_level: Optional[int] = None  # UPower warning level: 1=None, 2=Discharging, 3=Low, 4=Critical, 5=Action

    def get_icon(self) -> str:
        """Get appropriate battery icon based on state and level."""
        # Calculate the battery level bucket (0-10)
        level = max(0, min(10, int(self.percent / 10)))

        if self.percent < 10 and not self.plugged:
            return "mdi:battery-alert"

        # Build icon name
        base = "mdi:battery"
        if self.plugged:
            base += "-charging"

        if level <= 10:
            base += f"-{level * 10}"
        else:
            # Shouldn't happen - percent > 100%
            logger.warning(f"Battery percentage {self.percent}% exceeds 100%")
            return "mdi:battery-unknown"

        return base


class BatteryDataProvider(ABC):
    """Abstract base class for battery data providers."""

    @abstractmethod
    async def discover_batteries(self) -> List[str]:
        """Discover available battery identifiers."""
        pass

    @abstractmethod
    async def get_battery_data(self, battery_id: str) -> Optional[BatteryData]:
        """Get data for a specific battery."""
        pass