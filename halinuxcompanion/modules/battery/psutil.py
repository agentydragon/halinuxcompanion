"""Battery data provider using psutil."""

import logging

import psutil

from .provider import BatteryData, BatteryDataProvider

logger = logging.getLogger(__name__)

# psutil only provides aggregated battery info
PSUTIL_BATTERY_ID = "main"


class PsutilBatteryProvider(BatteryDataProvider):
    """Battery data provider using psutil."""

    async def discover_batteries(self) -> list[str]:
        """Discover available batteries using psutil."""
        if psutil.sensors_battery():
            return [PSUTIL_BATTERY_ID]
        return []

    async def get_battery_data(self, battery_id: str) -> BatteryData | None:
        """Get battery data using psutil."""
        assert battery_id == PSUTIL_BATTERY_ID

        if not (battery := psutil.sensors_battery()):
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
            percent=battery.percent,
            plugged=battery.power_plugged,
            state=state,
            time_to_empty=battery.secsleft if battery.secsleft != -1 and not battery.power_plugged else None,
        )
