"""Test Bluetooth module robustness for adapter/device up/down scenarios."""

import asyncio

import pytest
from dbus_fast.aio import MessageBus
from hamcrest import assert_that, equal_to, has_item, has_properties

from halinuxcompanion.modules.base import SensorUpdate
from halinuxcompanion.modules.bluetooth import BluetoothModule
from halinuxcompanion.test_bluez_service import MockBlueZDaemon


@pytest.fixture
async def mock_bluez():
    """Create a mock BlueZ daemon for testing."""
    daemon = MockBlueZDaemon()
    await daemon.start()
    yield daemon
    await daemon.stop()


@pytest.fixture
async def module_and_bus(mock_bluez):
    """Create a Bluetooth module and bus connected to mock BlueZ."""
    bus = MessageBus(bus_address=mock_bluez._bus_address)
    await bus.connect()

    module = BluetoothModule(system_bus=bus, whitelisted_devices=["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"])

    yield module, bus, mock_bluez
    bus.disconnect()


@pytest.mark.asyncio
async def test_adapter_removal_and_reappearance(module_and_bus):
    """Test that module handles adapter removal and reappearance gracefully."""
    module, bus, mock_bluez = module_and_bus
    updates = []

    async def capture_update(update: SensorUpdate):
        updates.append(update)

    # Start monitoring
    await module.start(capture_update)

    # Initial state - adapter should be found
    await asyncio.sleep(0.1)  # Let initial updates process
    initial_updates = updates.copy()
    updates.clear()

    # Should have adapter enabled update
    assert_that(initial_updates, has_item(has_properties(unique_id="bluetooth_enabled", state=True)))

    # Remove adapter
    await mock_bluez.remove_adapter()
    await asyncio.sleep(0.1)  # Let removal process

    # Should get adapter unavailable update
    assert_that(updates, has_item(has_properties(unique_id="bluetooth_enabled", state=None)))
    updates.clear()

    # Re-add adapter
    await mock_bluez.add_adapter("/org/bluez/hci1", "11:22:33:44:55:66")
    await asyncio.sleep(0.1)  # Let addition process

    # Should get adapter available update
    assert_that(updates, has_item(has_properties(unique_id="bluetooth_enabled", state=True)))


@pytest.mark.asyncio
async def test_device_connect_disconnect_with_battery(module_and_bus):
    """Test device connection/disconnection with battery monitoring."""
    module, bus, mock_bluez = module_and_bus
    updates = []

    async def capture_update(update: SensorUpdate):
        updates.append(update)

    # Start monitoring
    await module.start(capture_update)
    await asyncio.sleep(0.1)
    updates.clear()

    # The device AA:BB:CC:DD:EE:FF already exists, just connect it
    await mock_bluez.set_device_connected("AA:BB:CC:DD:EE:FF", True, rssi=-65)
    await mock_bluez.set_device_battery("AA:BB:CC:DD:EE:FF", 75)
    await asyncio.sleep(0.1)

    # Should get device connected and battery updates
    device_updates = [u for u in updates if "aa_bb_cc_dd_ee_ff" in u.unique_id]

    # Verify connected state
    connected_update = next(u for u in device_updates if "connected" in u.unique_id)
    assert_that(connected_update.state, equal_to(True))

    # Verify battery state
    battery_update = next(u for u in device_updates if "battery" in u.unique_id)
    assert_that(battery_update.state, equal_to(75))
    updates.clear()

    # Disconnect device
    await mock_bluez.set_device_connected("AA:BB:CC:DD:EE:FF", False)
    await asyncio.sleep(0.1)

    # Should get disconnected update
    assert_that(
        updates, has_item(has_properties(unique_id="bluetooth_device_aa_bb_cc_dd_ee_ff_connected", state=False))
    )
    updates.clear()

    # Remove device entirely
    device_path = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
    await mock_bluez.remove_device(device_path)
    await asyncio.sleep(0.1)

    # Should get unavailable updates
    device_updates = [u for u in updates if "aa_bb_cc_dd_ee_ff" in u.unique_id]
    for update in device_updates:
        assert_that(update.state, equal_to(None))


@pytest.mark.asyncio
async def test_battery_interface_appears_later(module_and_bus):
    """Test battery interface appearing after device is already connected."""
    module, bus, mock_bluez = module_and_bus
    updates = []

    async def capture_update(update: SensorUpdate):
        updates.append(update)

    # Start monitoring
    await module.start(capture_update)
    await asyncio.sleep(0.1)
    updates.clear()

    # Device AA:BB:CC:DD:EE:FF already exists with battery, let's use a different device
    # Use the second device which doesn't have battery by default
    await mock_bluez.set_device_connected("11:22:33:44:55:66", True, rssi=-70)
    device_path = "/org/bluez/hci0/dev_11_22_33_44_55_66"
    await asyncio.sleep(0.1)

    # When connecting, we should get connected and rssi updates
    assert_that(updates, has_item(has_properties(unique_id="bluetooth_device_11_22_33_44_55_66_connected", state=True)))
    updates.clear()

    # Add battery interface
    await mock_bluez.add_battery_to_device(device_path, 50)
    await asyncio.sleep(0.1)

    # Should get battery update for device 11:22:33:44:55:66
    assert_that(updates, has_item(has_properties(unique_id="bluetooth_device_11_22_33_44_55_66_battery", state=50)))
