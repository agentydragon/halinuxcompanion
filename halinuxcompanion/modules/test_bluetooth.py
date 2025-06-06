"""Unit tests for Bluetooth module."""

import asyncio

import pytest
from dbus_fast.aio import MessageBus
from hamcrest import assert_that, has_item, has_items, has_properties

from halinuxcompanion.modules.base import DeviceClass, SensorUpdate
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
async def module(mock_bluez):
    """Create a Bluetooth module connected to mock BlueZ."""
    # Ensure mock daemon is properly started
    if not mock_bluez._bus_address:
        raise RuntimeError("Mock BlueZ daemon not properly started")

    bus = MessageBus(bus_address=mock_bluez._bus_address)
    await bus.connect()

    # Test with two whitelisted devices
    module = BluetoothModule(system_bus=bus, whitelisted_devices=["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"])
    yield module
    bus.disconnect()


@pytest.mark.asyncio
async def test_bluetooth_sensors_registration(module):
    """Test that Bluetooth module registers correct sensors."""
    sensors = module.sensors()

    # Should have: 1 adapter sensor + 4 sensors per device * 2 devices = 9 total
    assert len(sensors) == 9

    # Check adapter sensor
    adapter_sensor = next(s for s in sensors if s.unique_id == "bluetooth_enabled")
    assert adapter_sensor.name == "Bluetooth"
    assert adapter_sensor.type == "binary_sensor"
    assert adapter_sensor.device_class == DeviceClass.CONNECTIVITY

    # Check device sensors for first MAC
    device1_connected = next(s for s in sensors if s.unique_id == "bluetooth_device_aa_bb_cc_dd_ee_ff_connected")
    assert device1_connected.name == "Bluetooth AA:BB:CC:DD:EE:FF"
    assert device1_connected.type == "binary_sensor"
    assert device1_connected.device_class == DeviceClass.CONNECTIVITY

    device1_rssi = next(s for s in sensors if s.unique_id == "bluetooth_device_aa_bb_cc_dd_ee_ff_rssi")
    assert device1_rssi.name == "Bluetooth AA:BB:CC:DD:EE:FF RSSI"
    assert device1_rssi.unit_of_measurement == "dBm"

    device1_battery = next(s for s in sensors if s.unique_id == "bluetooth_device_aa_bb_cc_dd_ee_ff_battery")
    assert device1_battery.name == "Bluetooth AA:BB:CC:DD:EE:FF Battery"
    assert device1_battery.unit_of_measurement == "%"
    assert device1_battery.device_class == DeviceClass.BATTERY


@pytest.mark.asyncio
async def test_bluetooth_initial_state(module, mock_bluez, capture_updates):
    """Test initial Bluetooth state reading."""
    async with module.context(capture_updates):
        # Wait for initial updates
        await asyncio.sleep(0.1)

    # Should have received updates for adapter + 2 devices * 4 sensors each = 9 updates
    assert len(capture_updates) == 9

    # Check adapter state (mock starts enabled)
    assert_that(
        capture_updates,
        has_items(
            has_properties(unique_id="bluetooth_enabled", state=True, icon="mdi:bluetooth"),
        ),
    )


@pytest.mark.asyncio
async def test_bluetooth_adapter_state_changes(module, mock_bluez, capture_updates):
    """Test Bluetooth adapter enable/disable handling."""
    update_event = asyncio.Event()

    async def capture_with_event(update: SensorUpdate):
        await capture_updates(update)
        if update.unique_id == "bluetooth_enabled":
            update_event.set()

    async with module.context(capture_with_event):
        # Clear initial updates
        await asyncio.sleep(0.1)
        capture_updates.clear()
        update_event.clear()

        # Disable adapter
        await mock_bluez.set_adapter_powered(False)

        # Wait for update
        await asyncio.wait_for(update_event.wait(), timeout=1.0)

        # Check update with PyHamcrest
        assert_that(
            capture_updates,
            has_item(has_properties(unique_id="bluetooth_enabled", state=False, icon="mdi:bluetooth-off")),
        )

        # Re-enable adapter
        capture_updates.clear()
        update_event.clear()
        await mock_bluez.set_adapter_powered(True)
        await asyncio.wait_for(update_event.wait(), timeout=1.0)

        assert_that(
            capture_updates, has_item(has_properties(unique_id="bluetooth_enabled", state=True, icon="mdi:bluetooth"))
        )


@pytest.mark.asyncio
async def test_bluetooth_device_connection(module, mock_bluez):
    """Test Bluetooth device connection state changes."""
    updates = []
    update_event = asyncio.Event()

    async def capture_update(update: SensorUpdate):
        updates.append(update)
        if "connected" in update.unique_id:
            update_event.set()

    async with module.context(capture_update):
        # Clear initial updates
        await asyncio.sleep(0.1)
        updates.clear()
        update_event.clear()

        # Connect first device
        await mock_bluez.set_device_connected("AA:BB:CC:DD:EE:FF", True, rssi=-65)

        # Wait for updates
        await asyncio.wait_for(update_event.wait(), timeout=1.0)
        await asyncio.sleep(0.1)  # Let all updates complete

        # Check updates for first device
        assert_that(
            updates,
            has_items(
                has_properties(
                    unique_id="bluetooth_device_aa_bb_cc_dd_ee_ff_connected", state=True, icon="mdi:bluetooth-connect"
                ),
                has_properties(unique_id="bluetooth_device_aa_bb_cc_dd_ee_ff_rssi", state=-65),
            ),
        )


@pytest.mark.asyncio
async def test_bluetooth_device_battery(module, mock_bluez, capture_updates):
    """Test Bluetooth device battery level reporting."""
    battery_event = asyncio.Event()

    # Wrap capture_updates to add event signaling
    async def capture_with_event(update: SensorUpdate):
        await capture_updates(update)
        if "battery" in update.unique_id:
            battery_event.set()

    async with module.context(capture_with_event):
        # Clear initial updates
        await asyncio.sleep(0.1)
        capture_updates.clear()
        battery_event.clear()

        # Set battery level for first device
        await mock_bluez.set_device_battery("AA:BB:CC:DD:EE:FF", 75)

        # Wait for update
        await asyncio.wait_for(battery_event.wait(), timeout=1.0)

        # Check battery update with PyHamcrest
        assert_that(
            capture_updates,
            has_item(
                has_properties(
                    unique_id="bluetooth_device_aa_bb_cc_dd_ee_ff_battery", state=75, icon="mdi:battery-bluetooth-70"
                )
            ),
        )


@pytest.mark.asyncio
async def test_bluetooth_device_name_alias(module, mock_bluez):
    """Test Bluetooth device name/alias reporting."""
    updates = []

    async def capture_update(update: SensorUpdate):
        updates.append(update)

    async with module.context(capture_update):
        # Clear initial updates
        await asyncio.sleep(0.1)
        updates.clear()

        # Update device name
        await mock_bluez.set_device_name("AA:BB:CC:DD:EE:FF", "My Headphones")
        await asyncio.sleep(0.2)

        # Check name update
        name_updates = [u for u in updates if u.unique_id == "bluetooth_device_aa_bb_cc_dd_ee_ff_name"]
        assert any(u.state == "My Headphones" for u in name_updates)


@pytest.mark.asyncio
async def test_bluetooth_unavailable_state(mock_bluez, capture_updates):
    """Test handling of unavailable Bluetooth service."""
    # Create module directly without fixture to control lifecycle
    bus = MessageBus(bus_address=mock_bluez._bus_address)
    await bus.connect()

    module = BluetoothModule(system_bus=bus, whitelisted_devices=["AA:BB:CC:DD:EE:FF"])

    async with module.context(capture_updates):
        # Clear initial updates
        await asyncio.sleep(0.1)
        capture_updates.clear()

        # Stop the daemon to simulate service failure
        await mock_bluez.stop()

        # Force an update that will fail (now with timeouts in the module)
        await module._update()

        # Check that unavailable state was sent using PyHamcrest
        assert_that(capture_updates, has_item(has_properties(unique_id="bluetooth_enabled", state=None)))

        # Also check device sensors got unavailable states
        device_ids = [f"bluetooth_device_{mac.replace(':', '_').lower()}_connected" for mac in ["AA:BB:CC:DD:EE:FF"]]
        for device_id in device_ids:
            assert_that(capture_updates, has_item(has_properties(unique_id=device_id)))

    bus.disconnect()


@pytest.mark.parametrize(
    ("percentage", "expected_icon"),
    [
        (100, "mdi:battery-bluetooth"),
        (75, "mdi:battery-bluetooth-70"),
        (50, "mdi:battery-bluetooth-50"),
        (25, "mdi:battery-bluetooth-20"),
        (10, "mdi:battery-bluetooth-10"),
        (0, "mdi:battery-alert-bluetooth"),
        (None, "mdi:battery-bluetooth-variant"),
    ],
)
def test_bluetooth_battery_icon_selection(percentage, expected_icon):
    """Test battery icon selection based on percentage."""
    assert BluetoothModule._get_battery_icon(percentage) == expected_icon
