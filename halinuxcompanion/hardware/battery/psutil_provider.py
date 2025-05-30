"""Battery data provider using psutil."""

import asyncio
import logging
from typing import List, Optional

import psutil

from .provider import BatteryData, BatteryDataProvider

logger = logging.getLogger(__name__)

# psutil only provides aggregated battery info
PSUTIL_BATTERY_ID = "main"


class PsutilBatteryProvider(BatteryDataProvider):
    """Battery data provider using psutil."""

    async def discover_batteries(self) -> List[str]:
        """Discover available batteries using psutil."""
        battery = await asyncio.get_event_loop().run_in_executor(
            None, psutil.sensors_battery
        )
        if battery:
            return [PSUTIL_BATTERY_ID]
        return []

    async def get_battery_data(self, battery_id: str) -> Optional[BatteryData]:
        """Get battery data using psutil."""
        if battery_id != PSUTIL_BATTERY_ID:
            return None

        battery = await asyncio.get_event_loop().run_in_executor(
            None, psutil.sensors_battery
        )
        if not battery:
            return None

        # Determine battery state
        if not battery.power_plugged:
            state = "Discharging"
        elif battery.percent >= 100:
            state = "Full"
        else:
            state = "Charging"

        return BatteryData(
            battery_id=battery_id,
            name="Battery",
            percent=battery.percent,
            plugged=battery.power_plugged,
            state=state,
            time_to_empty=battery.secsleft
            if battery.secsleft != -1 and not battery.power_plugged
            else None,
        )
