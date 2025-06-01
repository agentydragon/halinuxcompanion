"""Battery data provider base classes and interfaces."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BatteryData:
    """Unified battery data structure."""

    # Identity
    battery_id: str

    # Basic info
    percent: float
    plugged: bool
    state: str  # "Charging", "Discharging", "Full", "Unknown"

    # Time estimates
    time_to_empty: int | None = None  # seconds
    time_to_full: int | None = None  # seconds

    # Power/energy metrics
    charge_rate: float | None = None  # W
    discharge_rate: float | None = None  # W
    energy: float | None = None  # Wh
    energy_full: float | None = None  # Wh
    energy_full_design: float | None = None  # Wh

    # Battery health
    capacity: float | None = None  # percentage (0-100)
    charge_cycles: int | None = None

    # Physical properties
    voltage: float | None = None  # V
    temperature: float | None = None  # °C

    # Device info not pulled: technology, model, vendor, serial, upower warning_level

    def get_icon(self) -> str:
        """Get appropriate battery icon based on state and level."""
        # Calculate the battery level bucket (0-10)
        parts = ["mdi:battery"]
        if self.percent > 100:
            logger.warning(f"Battery percentage {self.percent}% exceeds 100%")
            parts.append("unknown")
            return "-".join(parts)
        if self.percent < 10 and not self.plugged:
            parts.append("alert")
            return "-".join(parts)
        if self.plugged:
            parts.append("charging")
        level = max(0, min(10, int(self.percent / 10)))
        parts.append(str(level * 10))
        return "-".join(parts)


class BatteryDataProvider(ABC):
    """Abstract base class for battery data providers."""

    @abstractmethod
    async def discover_batteries(self) -> list[str]:
        """Discover available battery identifiers."""

    @abstractmethod
    async def get_battery_data(self, battery_id: str) -> BatteryData | None:
        """Get data for a specific battery."""
