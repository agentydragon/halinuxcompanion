*** Settings ***
Documentation     Test Bluetooth state transition from OFF to ON
...               This test verifies that halinuxcompanion correctly handles
...               Bluetooth being turned on after it starts with Bluetooth off.

Library           Process
Library           OperatingSystem
Library           DateTime
Library           Dialogs
Library           ./HACompanionLibrary.py

Test Setup        Setup Test Case
Test Teardown     Teardown Test Case

*** Variables ***
${TEST_NAME}              bluetooth_off_to_on
${RESULTS_BASE_DIR}       ${CURDIR}/results
${COMPANION_PID}          ${NONE}
${TEST_DEVICE_MAC}        ${NONE}
${HA_TOKEN}               ${NONE}

*** Test Cases ***
Bluetooth Off To On With Device Connection
    [Documentation]    Verify device connection when Bluetooth transitions from OFF to ON
    [Tags]    bluetooth    manual    smoke

    # === STEP 1: Initial Setup - Bluetooth OFF ===
    Log To Console    \n${'='*60}
    Log To Console    STEP 1: Initial Setup - Ensure Bluetooth is OFF
    Log To Console    ${'='*60}\n

    Pause Execution    Please ensure Bluetooth is turned OFF in system settings, then press OK

    ${bluetooth_off}=    Get Value From User
    ...    Is Bluetooth currently OFF? (yes/no)
    ...    yes
    Should Be Equal    ${bluetooth_off}    yes
    ...    msg=Bluetooth must be OFF to start this test

    # Collect initial diagnostics
    Log    Collecting initial system diagnostics...
    Collect DBus Diagnostics    ${RESULTS_DIR}    01_initial_bt_off

    # === STEP 2: Start halinuxcompanion ===
    Log To Console    \n${'='*60}
    Log To Console    STEP 2: Starting halinuxcompanion
    Log To Console    ${'='*60}\n

    Ensure Process Not Running    halinuxcompanion
    ${pid}=    Start HALinuxCompanion With Logging    ${RESULTS_DIR}
    Set Test Variable    ${COMPANION_PID}    ${pid}

    Log To Console    ✓ halinuxcompanion started with PID: ${pid}
    Log To Console    ✓ Logs are being written to: ${RESULTS_DIR}/halinuxcompanion.log
    Sleep    3s    Wait for initial startup

    # Collect initial HA sensor state
    Collect HA Sensor Data    ${RESULTS_DIR}    02_initial_ha_data

    # === STEP 3: Verify device status in HA (should be disconnected) ===
    Log To Console    \n${'='*60}
    Log To Console    STEP 3: Check Home Assistant - Device Should Be Disconnected
    Log To Console    ${'='*60}\n

    Pause Execution    message=Open Home Assistant and navigate to your device.\nThe Bluetooth device should show as "Not Connected".\n\nPress OK when ready.

    ${device_visible}=    Get Selection From User
    ...    Is your Bluetooth device visible in Home Assistant?
    ...    Yes - Shows as disconnected
    ...    Yes - Shows as connected (UNEXPECTED)
    ...    No - Device not visible

    Should Be Equal    ${device_visible}    Yes - Shows as disconnected
    ...    msg=Device should be visible but disconnected when BT is off

    Take System Screenshot    ${RESULTS_DIR}    03_ha_device_disconnected

    # Optionally get device MAC for tracking
    ${track_device}=    Get Selection From User
    ...    Do you want to track a specific Bluetooth device?
    ...    Yes    No

    Run Keyword If    '${track_device}' == 'Yes'
    ...    ${TEST_DEVICE_MAC}=    Get Value From User
    ...    Enter the MAC address of your device (e.g., AA:BB:CC:DD:EE:FF):

    # === STEP 4: Turn Bluetooth ON ===
    Log To Console    \n${'='*60}
    Log To Console    STEP 4: Turn Bluetooth ON
    Log To Console    ${'='*60}\n

    Pause Execution    Please turn Bluetooth ON in system settings, then press OK

    ${bluetooth_on}=    Get Value From User
    ...    Is Bluetooth now ON? (yes/no)
    ...    yes
    Should Be Equal    ${bluetooth_on}    yes

    # Collect diagnostics after BT turned on
    Sleep    2s    Wait for Bluetooth to initialize
    Collect DBus Diagnostics    ${RESULTS_DIR}    04_after_bt_on

    # === STEP 5: Connect Bluetooth Device ===
    Log To Console    \n${'='*60}
    Log To Console    STEP 5: Connect Your Bluetooth Device
    Log To Console    ${'='*60}\n

    Run Keyword If    '${TEST_DEVICE_MAC}' != '${NONE}'
    ...    Log To Console    Tracking device: ${TEST_DEVICE_MAC}

    Pause Execution    Please connect your Bluetooth device now, then press OK

    ${device_connected}=    Get Value From User
    ...    Is your Bluetooth device now connected? (yes/no)
    ...    yes
    Should Be Equal    ${device_connected}    yes

    # === STEP 6: Verify in Home Assistant ===
    Log To Console    \n${'='*60}
    Log To Console    STEP 6: Verify Device Status in Home Assistant
    Log To Console    ${'='*60}\n

    Sleep    5s    Wait for HA to receive updates

    Pause Execution    Check your device in Home Assistant.\n\nIt should now show as "Connected".\nIf the device has a battery, it should show battery level.\n\nPress OK when ready.

    ${ha_status}=    Get Selection From User
    ...    What is the device status in Home Assistant?
    ...    Connected with battery level
    ...    Connected without battery
    ...    Still disconnected
    ...    Device not visible

    Should Contain    ${ha_status}    Connected
    ...    msg=Device should show as connected in HA

    Take System Screenshot    ${RESULTS_DIR}    06_ha_device_connected
    Collect DBus Diagnostics    ${RESULTS_DIR}    06_final_state
    Collect HA Sensor Data    ${RESULTS_DIR}    07_final_ha_data

    # === STEP 7: Optional Notes ===
    ${add_notes}=    Get Selection From User
    ...    Would you like to add notes about this test?
    ...    Yes    No

    Run Keyword If    '${add_notes}' == 'Yes'    Collect Test Notes

*** Keywords ***
Setup Test Case
    [Documentation]    Set up test environment
    ${timestamp}=    Get Current Date    result_format=%Y%m%d_%H%M%S
    ${test_dir}=    Set Variable    ${RESULTS_BASE_DIR}/${TEST_NAME}_${timestamp}
    Create Directory    ${test_dir}
    Set Test Variable    ${RESULTS_DIR}    ${test_dir}
    Set Test Variable    ${TEST_START_TIME}    ${timestamp}

    Log To Console    \n${'#'*60}
    Log To Console    # Test: Bluetooth OFF → ON Scenario
    Log To Console    # Time: ${timestamp}
    Log To Console    # Results: ${test_dir}
    Log To Console    ${'#'*60}\n

    # Check if Home Assistant is available and get token if needed
    Setup Home Assistant Connection

Teardown Test Case
    [Documentation]    Clean up test environment
    Log To Console    \n${'='*60}
    Log To Console    Test Cleanup
    Log To Console    ${'='*60}\n

    # Stop halinuxcompanion if running
    Run Keyword If    '${COMPANION_PID}' != '${NONE}'
    ...    Stop HALinuxCompanion    ${COMPANION_PID}

    # Generate test summary
    Generate Test Summary

    Log To Console    \n✓ Test completed. Results saved to:
    Log To Console    ${RESULTS_DIR}

Generate Test Summary
    [Documentation]    Generate a summary of the test results
    ${end_time}=    Get Current Date    result_format=%Y%m%d_%H%M%S
    ${summary}=    Catenate    SEPARATOR=\n
    ...    # Test Summary: Bluetooth OFF → ON
    ...
    ...    **Test ID:** ${TEST_NAME}_${TEST_START_TIME}
    ...    **Start Time:** ${TEST_START_TIME}
    ...    **End Time:** ${end_time}
    ...    **Status:** ${TEST STATUS}
    ...
    ...    ## Test Steps:
    ...    1. Started with Bluetooth OFF
    ...    2. Started halinuxcompanion
    ...    3. Verified device shows as disconnected in HA
    ...    4. Turned Bluetooth ON
    ...    5. Connected Bluetooth device
    ...    6. Verified device shows as connected in HA
    ...
    ...    ## Collected Diagnostics:
    ...    - DBus dumps at each stage
    ...    - halinuxcompanion debug logs
    ...    - DBus monitor logs
    ...    - System screenshots
    ...
    ...    ## Files:
    ...    - halinuxcompanion.log - Application logs
    ...    - dbus_monitor.log - DBus traffic
    ...    - *_dbus_diagnostics.json - System state snapshots
    ...    - *.png - Screenshots

    Create File    ${RESULTS_DIR}/summary.md    ${summary}

Collect Test Notes
    [Documentation]    Collect additional notes from tester
    ${notes}=    Get Multiline Value From User
    ...    Enter any additional notes about this test:
    ...
    ${timestamp}=    Get Current Date
    ${note_content}=    Catenate    SEPARATOR=\n
    ...    # Test Notes
    ...    **Timestamp:** ${timestamp}
    ...    **Tester Notes:**
    ...
    ...    ${notes}

    Create File    ${RESULTS_DIR}/test_notes.md    ${note_content}

Setup Home Assistant Connection
    [Documentation]    Setup connection to Home Assistant
    ${ha_available}=    Verify Home Assistant Available

    Run Keyword If    not ${ha_available}
    ...    Run Keywords
    ...    Log To Console    \nHome Assistant not available at default URL.
    ...    AND    ${start_docker}=    Get Selection From User
    ...        Start Home Assistant in Docker?    Yes    No    Use existing
    ...    AND    Run Keyword If    '${start_docker}' == 'Yes'
    ...        Start Home Assistant Docker

    # Get HA token if we don't have one
    ${token}=    Get Variable Value    ${HA_TOKEN}    ${NONE}
    Run Keyword If    '${token}' == '${NONE}'
    ...    Run Keywords
    ...    Log To Console    \nTo collect Home Assistant sensor data, we need an access token.
    ...    AND    Log To Console    Get a token from: Settings -> Your User -> Security -> Long-lived access tokens
    ...    AND    ${token}=    Get Value From User    Enter Home Assistant access token (or press Cancel to skip):    SKIP
    ...    AND    Run Keyword If    '${token}' != 'SKIP'
    ...        Set HA Token    ${token}

    # Mark test start time for history collection
    Mark Test Start
