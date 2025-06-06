"""Test program demonstrating Bluetooth sensor with mock BlueZ service."""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from dbus_fast.aio import MessageBus

from halinuxcompanion.modules.base import SensorUpdate
from halinuxcompanion.modules.bluetooth import BluetoothModule
from halinuxcompanion.test_bluez_service import MockBlueZDaemon

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BluetoothDemo:
    """Demo application showing Bluetooth sensor updates."""

    def __init__(self):
        self.bluetooth_module = None
        self.updates_received = []

    async def on_sensor_update(self, update: SensorUpdate):
        """Handle sensor updates from Bluetooth module."""
        self.updates_received.append(update)
        logger.info(f"Sensor update: {update.unique_id} = {update.state}")
        if update.icon:
            logger.info(f"  Icon: {update.icon}")
        if update.attributes:
            logger.info(f"  Attributes: {update.attributes}")

    async def run(self):
        """Run the demo."""
        # Start mock BlueZ daemon
        async with MockBlueZDaemon() as daemon:
            logger.info("Mock BlueZ daemon started")

            # Connect to the private bus
            bus = MessageBus(bus_address=daemon._bus_address)
            await bus.connect()
            logger.info("Connected to private DBus")

            # Create Bluetooth module with two whitelisted devices
            self.bluetooth_module = BluetoothModule(
                system_bus=bus, whitelisted_devices=["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]
            )

            # Get sensor registrations
            sensors = self.bluetooth_module.sensors()
            logger.info("\nRegistered sensors:")
            for sensor in sensors:
                logger.info(f"  - {sensor.name} ({sensor.unique_id})")
                logger.info(f"    Type: {sensor.type}")
                if sensor.unit_of_measurement:
                    logger.info(f"    Unit: {sensor.unit_of_measurement}")
                if sensor.device_class:
                    logger.info(f"    Device class: {sensor.device_class}")

            # Start the module
            await self.bluetooth_module.start(self.on_sensor_update)
            logger.info("\nBluetooth module started, waiting for initial state...")

            # Wait for initial updates
            await asyncio.sleep(1)

            # Simulate Bluetooth changes
            logger.info("\n=== Disabling Bluetooth adapter ===")
            await daemon.set_adapter_powered(False)
            await asyncio.sleep(2)

            logger.info("\n=== Re-enabling Bluetooth adapter ===")
            await daemon.set_adapter_powered(True)
            await asyncio.sleep(2)

            logger.info("\n=== Connecting first device with RSSI ===")
            await daemon.set_device_connected("AA:BB:CC:DD:EE:FF", True, rssi=-65)
            await daemon.set_device_name("AA:BB:CC:DD:EE:FF", "My Headphones")
            await asyncio.sleep(2)

            logger.info("\n=== Setting battery level for first device ===")
            await daemon.set_device_battery("AA:BB:CC:DD:EE:FF", 75)
            await asyncio.sleep(2)

            logger.info("\n=== Connecting second device ===")
            await daemon.set_device_connected("11:22:33:44:55:66", True, rssi=-72)
            await daemon.set_device_name("11:22:33:44:55:66", "Wireless Mouse")
            await asyncio.sleep(2)

            logger.info("\n=== Low battery warning on first device ===")
            await daemon.set_device_battery("AA:BB:CC:DD:EE:FF", 15)
            await asyncio.sleep(2)

            logger.info("\n=== Disconnecting first device ===")
            await daemon.set_device_connected("AA:BB:CC:DD:EE:FF", False)
            await asyncio.sleep(2)

            # Stop the module
            await self.bluetooth_module.stop()
            logger.info("\nBluetooth module stopped")

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

            for sensor_id, updates in sorted(updates_by_sensor.items()):
                logger.info(f"\n{sensor_id}: {len(updates)} updates")
                for i, update in enumerate(updates[-3:]):  # Show last 3 updates
                    logger.info(f"  [{i + 1}] State: {update.state}, Icon: {update.icon}")


async def main():
    """Run the Bluetooth demo."""
    demo = BluetoothDemo()
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())
