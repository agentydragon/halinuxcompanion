"""Tests for battery provider functionality."""

from halinuxcompanion.hardware.battery_providers.battery_provider import BatteryData


class TestBatteryData:
    """Test BatteryData class methods."""

    def test_get_icon_charging_states(self):
        """Test battery icon generation for different charging states."""
        test_cases = [
            # (percent, plugged, state, expected_icon)
            (100.0, True, "Full", "mdi:battery-charging-100"),
            (91.0, True, "Charging", "mdi:battery-charging-90"),
            (85.0, True, "Charging", "mdi:battery-charging-80"),
            (75.0, True, "Charging", "mdi:battery-charging-70"),
            (65.0, True, "Charging", "mdi:battery-charging-60"),
            (55.0, True, "Charging", "mdi:battery-charging-50"),
            (45.0, True, "Charging", "mdi:battery-charging-40"),
            (35.0, True, "Charging", "mdi:battery-charging-30"),
            (25.0, True, "Charging", "mdi:battery-charging-20"),
            (15.0, True, "Charging", "mdi:battery-charging-10"),
            (5.0, True, "Charging", "mdi:battery-charging-0"),
        ]

        for percent, plugged, state, expected_icon in test_cases:
            data = BatteryData(
                battery_id="BAT0",
                name="Test Battery",
                percent=percent,
                plugged=plugged,
                state=state,
            )
            assert data.get_icon() == expected_icon

    def test_get_icon_discharging_states(self):
        """Test battery icon generation for discharging states."""
        test_cases = [
            # (percent, plugged, state, expected_icon)
            (100.0, False, "Discharging", "mdi:battery-100"),
            (91.0, False, "Discharging", "mdi:battery-90"),
            (85.0, False, "Discharging", "mdi:battery-80"),
            (75.0, False, "Discharging", "mdi:battery-70"),
            (65.0, False, "Discharging", "mdi:battery-60"),
            (55.0, False, "Discharging", "mdi:battery-50"),
            (45.0, False, "Discharging", "mdi:battery-40"),
            (35.0, False, "Discharging", "mdi:battery-30"),
            (25.0, False, "Discharging", "mdi:battery-20"),
            (15.0, False, "Discharging", "mdi:battery-10"),
            (10.0, False, "Discharging", "mdi:battery-10"),
        ]

        for percent, plugged, state, expected_icon in test_cases:
            data = BatteryData(
                battery_id="BAT0",
                name="Test Battery",
                percent=percent,
                plugged=plugged,
                state=state,
            )
            assert data.get_icon() == expected_icon

    def test_get_icon_low_battery_alert(self):
        """Test battery alert icon for critically low battery."""
        test_cases = [
            # (percent, plugged, expected_icon)
            (9.9, False, "mdi:battery-alert"),
            (5.0, False, "mdi:battery-alert"),
            (0.0, False, "mdi:battery-alert"),
            # Alert doesn't show when plugged in
            (9.9, True, "mdi:battery-charging-0"),
            (5.0, True, "mdi:battery-charging-0"),
        ]

        for percent, plugged, expected_icon in test_cases:
            data = BatteryData(
                battery_id="BAT0",
                name="Test Battery",
                percent=percent,
                plugged=plugged,
                state="Discharging" if not plugged else "Charging",
            )
            assert data.get_icon() == expected_icon

    def test_get_icon_edge_cases(self):
        """Test battery icon generation for edge cases."""
        # Test exact boundaries
        boundaries = [
            (0.0, False, "mdi:battery-alert"),
            (10.0, False, "mdi:battery-10"),
            (20.0, False, "mdi:battery-20"),
            (30.0, False, "mdi:battery-30"),
            (40.0, False, "mdi:battery-40"),
            (50.0, False, "mdi:battery-50"),
            (60.0, False, "mdi:battery-60"),
            (70.0, False, "mdi:battery-70"),
            (80.0, False, "mdi:battery-80"),
            (90.0, False, "mdi:battery-90"),
            (100.0, False, "mdi:battery-100"),
        ]

        for percent, plugged, expected_icon in boundaries:
            data = BatteryData(
                battery_id="BAT0",
                name="Test Battery",
                percent=percent,
                plugged=plugged,
                state="Discharging",
            )
            assert data.get_icon() == expected_icon
