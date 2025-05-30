"""Tests for battery sensors using real hardware."""

import pytest

from .battery_psutil import PSUtilSensor
from .battery_upower import (
    UPowerSensor,
    UPowerVoltageSensor,
)


@pytest.fixture
async def psutil_sensors():
    """Get PSUtil battery sensors."""
    sensors = await PSUtilSensor.discover_sensors()
    if not sensors:
        pytest.skip("No battery detected by psutil")
    return sensors


@pytest.fixture
async def upower_sensors():
    """Get UPower battery sensors."""
    sensors = await UPowerSensor.discover_sensors()
    if not sensors:
        pytest.skip("No battery detected by UPower")
    return sensors


@pytest.fixture
async def bat0_sensor(upower_sensors):
    """Get BAT0 sensor specifically."""
    for sensor in upower_sensors:
        if sensor.instance_id == "BAT0":
            return sensor
    pytest.skip("No BAT0 battery found")


async def validate_battery_sensor(sensor):
    """Common validation for any battery percentage sensor."""
    await sensor.update()

    # Check battery percentage is reasonable
    assert isinstance(sensor.state, (int, float))
    assert 0 <= sensor.state <= 100

    # Check required attributes
    assert isinstance(sensor.attributes["power_plugged"], bool)
    assert sensor.attributes["battery_state"] in [
        "Charging",
        "Discharging",
        "Full",
        "Unknown",
    ]


@pytest.mark.asyncio
@pytest.mark.requires_hardware
async def test_psutil_battery(psutil_sensors):
    """Test PSUtil battery sensor."""
    await validate_battery_sensor(psutil_sensors[0])


@pytest.mark.asyncio
@pytest.mark.requires_hardware
async def test_upower_battery_BAT0(bat0_sensor):
    """Test UPower battery sensor for BAT0."""
    await validate_battery_sensor(bat0_sensor)


@pytest.mark.asyncio
@pytest.mark.requires_hardware
async def test_upower_voltage_BAT0():
    """Test UPower voltage sensor for BAT0."""
    sensors = await UPowerVoltageSensor.discover_sensors()

    # Find BAT0 voltage sensor
    bat0_voltage = None
    for sensor in sensors:
        if sensor.instance_id == "BAT0":
            bat0_voltage = sensor
            break

    if not bat0_voltage:
        pytest.skip("No BAT0 voltage sensor found")

    await bat0_voltage.update()

    # Voltage should be available and reasonable for a laptop battery
    assert bat0_voltage.state != "unavailable"
    assert isinstance(bat0_voltage.state, (int, float))
    assert 0 < bat0_voltage.state < 20  # Most laptop batteries are under 20V
