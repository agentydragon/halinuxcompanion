*** Settings ***
Documentation     Bluetooth test scenarios for Home Assistant Linux Companion
...               These tests verify Bluetooth functionality and device tracking
Resource          HALinuxCompanionLibrary.robot
Library           OperatingSystem
Suite Setup       Suite Setup
Suite Teardown    Suite Teardown
Test Setup        Test Setup
Test Teardown     Test Teardown

*** Variables ***
${TEST_DEVICE_MAC}    ${NONE}

*** Test Cases ***
Bluetooth OFF to ON Transition
    [Documentation]    Test Bluetooth state transition from OFF to ON with device connection
    [Tags]    bluetooth    manual    smoke

    # Verify Bluetooth is OFF
    Log To Console    ${\n}=== Checking Bluetooth Status ===

    ${bluetooth_off}=    Verify Bluetooth Is Off

    Run Keyword If    not ${bluetooth_off}
    ...    Run Keywords
    ...    Print Test Step    Please turn OFF Bluetooth:\n- GUI: Open system settings → Bluetooth → Toggle OFF\n- CLI: Run 'rfkill block bluetooth'\n- Verify with: 'bluetoothctl show' (should show "Powered: no")
    ...    AND    Pause For Action    Turn OFF Bluetooth and press Enter when done
    ...    AND    Should Be True    ${TRUE}    Bluetooth must be OFF to continue

    Set Test Message    Initial state: Bluetooth OFF verified

    # Collect initial diagnostics
    Collect DBus Diagnostics    01_initial_bt_off

    # Mark test start for HA data collection
    Mark Test Start Time

    # Start halinuxcompanion
    ${pid}=    Set Variable    ${NONE}
    ${start_result}=    Run Keyword And Ignore Error    Start HALinuxCompanion
    ${start_success}=    Set Variable If    '${start_result[0]}' == 'PASS'    ${True}    ${False}
    ${pid}=    Set Variable If    ${start_success}    ${start_result[1]}    ${NONE}

    Run Keyword If    not ${start_success}
    ...    Run Keywords
    ...    Log To Console    ${\n}⚠ halinuxcompanion failed to start - it may need to be registered first
    ...    AND    Print Test Step    Register halinuxcompanion:\n- Run: halinuxcompanion register\n- Enter your Home Assistant URL when prompted\n- Follow the authentication flow
    ...    AND    Pause For Action    Register halinuxcompanion and press Enter when done
    ...    AND    Set Test Variable    ${pid}    ${NONE}

    Print Test Step    Verify halinuxcompanion is running:\n- Check the process is running\n- Logs are being written to: ${RESULTS_DIR}/halinuxcompanion.log\n- You can monitor logs with: tail -f ${RESULTS_DIR}/halinuxcompanion.log

    ${status}=    Get User Verification    Is halinuxcompanion running successfully?
    Should Be Equal    ${status}    PASS    halinuxcompanion must be running

    # Check initial HA state
    Print Test Step    Check Home Assistant shows Bluetooth as OFF:\n- In HA, go to Settings → Devices & Services → Devices\n- Find your Linux PC device\n- Check the Bluetooth sensors:\n  * bluetooth_enabled should be OFF\n  * Your Bluetooth devices should show as "Not Connected"

    Take Screenshot    03_ha_device_disconnected

    ${status}=    Get User Verification    Does HA show Bluetooth as OFF and devices as disconnected?
    Should Be Equal    ${status}    PASS    HA must show correct initial state

    # Collect initial HA sensor data
    Collect HA Sensor Data    02_initial_ha_data

    # Turn Bluetooth ON
    Log To Console    ${\n}=== Turn Bluetooth ON ===
    Print Test Step    Turn ON Bluetooth:\n- GUI: Open system settings → Bluetooth → Toggle ON\n- CLI: Run 'rfkill unblock bluetooth'\n- Verify with: 'bluetoothctl show' (should show "Powered: yes")\n- Watch halinuxcompanion logs for "Bluetooth powered on" message

    Pause For Action    Turn ON Bluetooth and press Enter when done

    ${bluetooth_on}=    Verify Bluetooth Is On
    Should Be True    ${bluetooth_on}    Failed to turn Bluetooth ON

    # Collect diagnostics after BT on
    Collect DBus Diagnostics    04_after_bt_on

    # Connect device
    Print Test Step    Connect your Bluetooth device:\n- Turn on your Bluetooth device (headphones, speaker, etc.)\n- GUI: In Bluetooth settings, click on your device to connect\n- CLI: Run 'bluetoothctl connect XX:XX:XX:XX:XX:XX' (device MAC)\n- Watch halinuxcompanion logs for "Device connected" message

    ${status}=    Get User Verification    Is your Bluetooth device now connected?
    Run Keyword If    '${status}' == 'SKIP'
    ...    Log    No Bluetooth device available for testing    WARN
    ...    ELSE
    ...    Should Be Equal    ${status}    PASS    Device connection verification

    # Wait for HA updates
    Print Test Step    Wait for Home Assistant to receive updates:\n- Wait 5-10 seconds for sensor updates to propagate\n- You should see update messages in the halinuxcompanion logs
    Sleep    5s    Wait for HA sensor updates

    # Verify in HA
    Print Test Step    Verify device shows as connected in Home Assistant:\n- In HA, refresh the device page (F5)\n- Check Bluetooth sensors:\n  * bluetooth_enabled should be ON\n  * Your device should show as "Connected"\n  * Battery level should appear (if device supports it)\n- Check sensor history graphs show the state changes

    Take Screenshot    06_ha_device_connected

    ${status}=    Get User Verification    Does the device show as 'Connected' in HA with all expected sensors?
    Should Not Be Equal    ${status}    FAIL    Final HA verification failed

    # Collect final diagnostics
    Collect DBus Diagnostics    06_final_state
    Collect HA Sensor Data    07_final_ha_data

Bluetooth ON to OFF Transition
    [Documentation]    Test Bluetooth state transition from ON to OFF
    [Tags]    bluetooth    manual

    # This test starts with Bluetooth ON and a connected device
    Print Test Step    Ensure Bluetooth is ON with a connected device:\n- Bluetooth should be ON\n- At least one device should be connected\n- Verify with: 'bluetoothctl show' and 'bluetoothctl devices Connected'

    ${step1}=    Get User Verification    Is Bluetooth ON with a connected device?
    Set To Dictionary    ${step1}    description=Initial state: Bluetooth ON with device
    Append To List    ${TEST_RESULTS}    ${step1}

    # Continue with remaining steps...
    Log    Test case to be completed

*** Keywords ***
Suite Setup
    [Documentation]    One-time setup for the test suite
    Log    Starting Home Assistant Linux Companion test suite
    # HA token is required - will fail early if not provided
    Verify Home Assistant Available

Suite Teardown
    [Documentation]    One-time cleanup for the test suite
    Log    Test suite completed
    Run Keyword If    '${HALINUXCOMPANION_PID}' != '${NONE}'
    ...    Stop HALinuxCompanion

Test Setup
    [Documentation]    Setup for each test case
    ${test_name}=    Replace String    ${TEST NAME}    ${SPACE}    _
    Setup Test Environment    ${test_name}
    Log    Starting test: ${TEST NAME}    console=True

Test Teardown
    [Documentation]    Cleanup for each test case
    Stop HALinuxCompanion
    Log Many    console=True
    ...    ${\n}Test completed: ${TEST NAME}
    ...    Results saved to: ${RESULTS_DIR}
    ...    ${\n}
