"""Bluetooth test scenarios for manual testing."""

from typing import Any


async def test_bluetooth_off_to_on(runner: Any) -> list[dict[str, Any]]:
    """Test Bluetooth state transition from OFF to ON."""
    steps = []

    # Collect initial diagnostics
    runner.collector.collect_dbus_diagnostics(str(runner.results_dir), "01_initial_bt_off")

    # Step 1: Verify Bluetooth is OFF
    runner.print_step(
        1,
        8,
        """Turn OFF Bluetooth:
    - GUI: Open system settings → Bluetooth → Toggle OFF
    - CLI: Run 'rfkill block bluetooth'
    - Verify with: 'bluetoothctl show' (should show "Powered: no")""",
    )
    result = runner.get_verification("Is Bluetooth currently OFF?", required=True)
    result["description"] = "Initial state: Bluetooth OFF"
    steps.append(result)

    # Mark test start time for HA data collection
    runner.env.ha_library.mark_test_start()

    # Use context manager for halinuxcompanion
    with runner.env.ha_library.halinuxcompanion_process(str(runner.results_dir)) as process:
        # Step 2: Start halinuxcompanion
        runner.print_step(
            2,
            8,
            f"""Start halinuxcompanion:
        - halinuxcompanion has been started automatically (PID: {process.pid})
        - Logs are being written to: {runner.results_dir}/halinuxcompanion.log
        - You can monitor logs with: tail -f {runner.results_dir}/halinuxcompanion.log""",
        )

        result = runner.get_verification(f"Can you see halinuxcompanion running? (PID: {process.pid})", required=True)
        result["description"] = "Start halinuxcompanion"
        steps.append(result)

        # Step 3: Register with Home Assistant
        runner.print_step(
            3,
            8,
            """Register halinuxcompanion with Home Assistant:
        - Open Home Assistant at http://localhost:8123
        - Go to Settings → Devices & Services → Integrations
        - Click "Add Integration" → Search for "Mobile App"
        - Enter any device name (e.g., "Test Linux PC")
        - Copy the webhook URL shown
        - In halinuxcompanion terminal, paste the webhook URL when prompted""",
        )
        result = runner.get_verification("Is halinuxcompanion registered with Home Assistant?", required=True)
        result["description"] = "Register halinuxcompanion with HA"
        steps.append(result)

        # Step 4: Check initial HA state
        runner.print_step(
            4,
            8,
            """Check Home Assistant shows Bluetooth as OFF:
        - In HA, go to Settings → Devices & Services → Devices
        - Find your Linux PC device
        - Check the Bluetooth sensors:
          * bluetooth_enabled should be OFF
          * Your Bluetooth devices should show as "Not Connected" """,
        )

        # Take screenshot
        runner.env.ha_library.take_system_screenshot(str(runner.results_dir), "03_ha_device_disconnected")

        result = runner.get_verification("Does HA show Bluetooth as OFF and devices as disconnected?", required=True)
        result["description"] = "Verify initial state in HA"
        steps.append(result)

        # Collect initial HA sensor data
        runner.env.ha_library.collect_ha_sensor_data(str(runner.results_dir), "02_initial_ha_data")

        # Step 5: Turn Bluetooth ON
        runner.print_step(
            5,
            8,
            """Turn ON Bluetooth:
        - GUI: Open system settings → Bluetooth → Toggle ON
        - CLI: Run 'rfkill unblock bluetooth'
        - Verify with: 'bluetoothctl show' (should show "Powered: yes")
        - Watch halinuxcompanion logs for "Bluetooth powered on" message""",
        )
        result = runner.get_verification("Is Bluetooth now ON?", required=True)
        result["description"] = "Turn Bluetooth ON"
        steps.append(result)

        # Collect diagnostics after BT on
        runner.collector.collect_dbus_diagnostics(str(runner.results_dir), "04_after_bt_on")

        # Step 6: Connect device
        runner.print_step(
            6,
            8,
            """Connect your Bluetooth device:
        - Turn on your Bluetooth device (headphones, speaker, etc.)
        - GUI: In Bluetooth settings, click on your device to connect
        - CLI: Run 'bluetoothctl connect XX:XX:XX:XX:XX:XX' (device MAC)
        - Watch halinuxcompanion logs for "Device connected" message""",
        )
        result = runner.get_verification("Is your Bluetooth device now connected?", required=True)
        result["description"] = "Connect Bluetooth device"
        steps.append(result)

        # Step 7: Wait for HA updates
        runner.print_step(
            7,
            8,
            """Wait for Home Assistant to receive updates:
        - Wait 5-10 seconds for sensor updates to propagate
        - You should see update messages in the halinuxcompanion logs""",
        )
        import time

        time.sleep(5)

        # Step 8: Verify in HA
        runner.print_step(
            8,
            8,
            """Verify device shows as connected in Home Assistant:
        - In HA, refresh the device page (F5)
        - Check Bluetooth sensors:
          * bluetooth_enabled should be ON
          * Your device should show as "Connected"
          * Battery level should appear (if device supports it)
        - Check sensor history graphs show the state changes""",
        )

        # Take final screenshot
        runner.env.ha_library.take_system_screenshot(str(runner.results_dir), "06_ha_device_connected")

        result = runner.get_verification(
            "Does the device show as 'Connected' in HA with all expected sensors?",
            required=True,
        )
        result["description"] = "Verify device shows as connected in HA"
        steps.append(result)

        # Collect final diagnostics
        runner.collector.collect_dbus_diagnostics(str(runner.results_dir), "06_final_state")
        runner.env.ha_library.collect_ha_sensor_data(str(runner.results_dir), "07_final_ha_data")

    return steps
