"""Unit tests for battery module."""

import asyncio

import pytest
from dbus_fast.aio import MessageBus
from hamcrest import assert_that, greater_than, has_items, has_properties

from halinuxcompanion.modules.base import SensorUpdate
from halinuxcompanion.modules.battery import BatteryModule, UPowerDeviceState
from halinuxcompanion.test_upower_service import MockUPowerDaemon

# logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
async def mock_upower():
    """Create a mock UPower daemon for testing."""
    daemon = MockUPowerDaemon()
    await daemon.start()
    yield daemon
    await daemon.stop()


@pytest.fixture
async def module(mock_upower):
    """Create a battery module connected to mock UPower."""
    # Ensure mock daemon is properly started
    if not mock_upower._bus_address:
        raise RuntimeError("Mock UPower daemon not properly started")

    bus = MessageBus(bus_address=mock_upower._bus_address)
    await bus.connect()
    module = BatteryModule(system_bus=bus)
    yield module
    bus.disconnect()


@pytest.mark.asyncio
async def test_battery_initial_state(module, mock_upower, capture_updates):
    """Test initial battery state reading."""
    async with module.context(capture_updates):
        # Wait for initial updates
        await asyncio.sleep(0.1)

    # Should have received 5 updates (one for each sensor)
    assert len(capture_updates) == 5

    # Check initial values (mock starts at 50% discharging)
    assert_that(
        capture_updates,
        has_items(
            has_properties(unique_id="battery_level", state=50.0, icon="mdi:battery-50"),
            has_properties(unique_id="battery_state", state="discharging", icon="mdi:battery-minus"),
        ),
    )


@pytest.mark.asyncio
async def test_battery_state_changes(module, mock_upower):
    """Test battery state change handling."""
    updates = []
    update_event = asyncio.Event()

    async def capture_update(update: SensorUpdate):
        updates.append(update)
        update_event.set()

    async with module.context(capture_update):
        # Clear initial updates
        await asyncio.sleep(0.1)
        updates.clear()
        update_event.clear()

        # Change to charging at 75%
        await mock_upower.update_battery(75.0, UPowerDeviceState.CHARGING, 20.0)

        # Wait for updates
        await asyncio.wait_for(update_event.wait(), timeout=1.0)
        await asyncio.sleep(0.1)  # Let all updates complete

        # Check updates
        assert len(updates) == 5

        assert_that(
            updates,
            has_items(
                has_properties(unique_id="battery_level", state=75.0, icon="mdi:battery-charging-70"),
                has_properties(unique_id="battery_state", state="charging", icon="mdi:battery-charging"),
                has_properties(unique_id="battery_power", state=-20.0),  # Negative when charging
                has_properties(unique_id="battery_time_to_empty", state=None),  # No time to empty when charging
                has_properties(unique_id="battery_time_to_full", state=greater_than(0)),
            ),
        )


@pytest.mark.parametrize(
    ("percentage", "state", "expected_icon"),
    [
        (5, UPowerDeviceState.CHARGING, "mdi:battery-charging-0"),
        (25, UPowerDeviceState.CHARGING, "mdi:battery-charging-20"),
        (100, UPowerDeviceState.CHARGING, "mdi:battery-charging-100"),
        (0, UPowerDeviceState.DISCHARGING, "mdi:battery-alert"),
        (5, UPowerDeviceState.DISCHARGING, "mdi:battery-alert"),
        (15, UPowerDeviceState.DISCHARGING, "mdi:battery-10"),
        (55, UPowerDeviceState.DISCHARGING, "mdi:battery-50"),
        (100, UPowerDeviceState.DISCHARGING, "mdi:battery"),
    ],
)
def test_battery_icon_selection(percentage, state, expected_icon):
    assert BatteryModule._get_battery_icon(percentage, state) == expected_icon


@pytest.mark.asyncio
async def test_battery_unavailable_state(module, mock_upower):
    """Test handling of unavailable battery (service failure)."""
    updates = []

    async def capture_update(update: SensorUpdate):
        updates.append(update)

    await module.start(capture_update)

    # Clear initial updates
    await asyncio.sleep(0.1)
    updates.clear()

    # Stop the daemon to simulate service failure
    await mock_upower.stop()

    # Force an update that will fail
    await module._update()

    # Check that unavailable state was sent
    assert len(updates) == 5
    for update in updates:
        assert update.state is None

    await module.stop()


@pytest.mark.asyncio
async def test_battery_module_lifecycle(module, mock_upower, capture_updates):
    """Test module start/stop lifecycle."""
    # Start and stop multiple times
    for _ in range(3):
        capture_updates.clear()
        async with module.context(capture_updates):
            await asyncio.sleep(0.1)

        # Should have received updates
        assert len(capture_updates) > 0

    # And update listener should be None
    assert module._update_listener is None
