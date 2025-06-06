#!/usr/bin/env python3
"""Test program demonstrating battery sensor with mock UPower service."""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dbus_fast.aio import MessageBus

from halinuxcompanion.modules.base import SensorUpdate
from halinuxcompanion.modules.battery import BatteryModule
from halinuxcompanion.test_upower_service import MockUPowerDaemon

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BatteryDemo:
    """Demo application showing battery sensor updates."""

    def __init__(self):
        self.battery_module = None
        self.updates_received = []

    async def on_sensor_update(self, update: SensorUpdate):
        """Handle sensor updates from battery module."""
        self.updates_received.append(update)
        logger.info(f"Sensor update: {update.unique_id} = {update.state}")
        if update.icon:
            logger.info(f"  Icon: {update.icon}")
        if update.attributes:
            logger.info(f"  Attributes: {update.attributes}")

    async def run(self):
        """Run the demo."""
        # Start mock UPower daemon
        async with MockUPowerDaemon() as daemon:
            logger.info("Mock UPower daemon started")

            # Connect to the private bus
            bus = MessageBus(bus_address=daemon._bus_address)
            await bus.connect()
            logger.info("Connected to private DBus")

            # Create battery module
            self.battery_module = BatteryModule(system_bus=bus)

            # Get sensor registrations
            sensors = self.battery_module.sensors()
            logger.info("\nRegistered sensors:")
            for sensor in sensors:
                logger.info(f"  - {sensor.name} ({sensor.unique_id})")
                logger.info(f"    Type: {sensor.type}")
                logger.info(f"    Unit: {sensor.unit_of_measurement}")
                logger.info(f"    Device class: {sensor.device_class}")

            # Start the module
            await self.battery_module.start(self.on_sensor_update)
            logger.info("\nBattery module started, waiting for initial state...")

            # Wait for initial updates
            await asyncio.sleep(1)

            # Simulate battery changes
            logger.info("\n=== Battery at 75% charging ===")
            await daemon.update_battery(75.0, 1, energy_rate=15.0)  # Charging
            await asyncio.sleep(2)

            logger.info("\n=== Battery at 100% fully charged ===")
            await daemon.update_battery(100.0, 4)  # Fully charged
            await asyncio.sleep(2)

            logger.info("\n=== Battery at 50% discharging ===")
            await daemon.update_battery(50.0, 2, energy_rate=10.0)  # Discharging
            await asyncio.sleep(2)

            logger.info("\n=== Battery at 15% discharging (low) ===")
            await daemon.update_battery(15.0, 2, energy_rate=5.0)  # Low battery
            await asyncio.sleep(2)

            logger.info("\n=== Battery at 5% discharging (critical) ===")
            await daemon.update_battery(5.0, 2, energy_rate=3.0)  # Critical
            await asyncio.sleep(2)

            # Stop the module
            await self.battery_module.stop()
            logger.info("\nBattery module stopped")

            # Disconnect from bus
            bus.disconnect()

            # Summary
            logger.info("\n=== Summary ===")
            logger.info(f"Total updates received: {len(self.updates_received)}")

            # Group updates by sensor
            updates_by_sensor: dict[str, list[SensorUpdate]] = {}
            for update in self.updates_received:
                if update.unique_id not in updates_by_sensor:
                    updates_by_sensor[update.unique_id] = []
                updates_by_sensor[update.unique_id].append(update)

            for sensor_id, updates in updates_by_sensor.items():
                logger.info(f"\n{sensor_id}: {len(updates)} updates")
                for i, update in enumerate(updates[-3:]):  # Show last 3 updates
                    logger.info(f"  [{i + 1}] State: {update.state}, Icon: {update.icon}")


async def main():
    """Run the battery demo."""
    demo = BatteryDemo()
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())
