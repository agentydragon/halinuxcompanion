*** Settings ***
Documentation     Battery test scenarios for Home Assistant Linux Companion
...               These tests verify battery monitoring and power state tracking
Resource          HALinuxCompanionLibrary.robot
Library           OperatingSystem
Suite Setup       Suite Setup
Suite Teardown    Suite Teardown
Test Setup        Test Setup
Test Teardown     Test Teardown

*** Test Cases ***
Battery State Monitoring
    [Documentation]    Test battery state monitoring and power transitions
    [Tags]    battery    manual

    # Check initial battery state
    Print Test Step    Check current battery/power state:\n- If on laptop: Note battery percentage and charging status\n- If on desktop: Should show as "plugged in" with no battery\n- Run: 'upower -i /org/freedesktop/UPower/devices/DisplayDevice'

    ${status}=    Get User Verification    Can you see the current power state?
    Should Be Equal    ${status}    PASS    Initial power state check failed

    # Mark test start and start halinuxcompanion
    Mark Test Start Time
    ${pid}=    Start HALinuxCompanion

    # Verify in Home Assistant
    Print Test Step    Check power sensors in Home Assistant:\n- Go to your device in HA\n- Look for battery/power sensors:\n  * battery_level (if laptop)\n  * battery_state (charging/discharging/full)\n  * battery_power (W)\n  * battery_time_to_empty/full (if applicable)

    Take Screenshot    01_initial_battery_state

    ${status}=    Get User Verification    Do you see the battery/power sensors in HA?
    Should Be Equal    ${status}    PASS    Power sensors not visible in HA

    # Change power state (if possible)
    Print Test Step    Change power state (if on laptop):\n- If currently charging: Unplug the charger\n- If on battery: Plug in the charger\n- If on desktop: Skip this step\n- Wait 10 seconds for the change to register

    ${status}=    Get User Verification    Did you change the power state (or skip if desktop)?
    Log    Power state change: ${status}    console=True

    Sleep    10s    Wait for power state change

    # Verify state change in HA
    Print Test Step    Verify power state change in Home Assistant:\n- Refresh the device page\n- Check if the battery_state sensor changed\n- Verify battery_power shows positive (charging) or negative (discharging)\n- Check if time estimates updated

    Take Screenshot    02_changed_battery_state

    ${status}=    Get User Verification    Did the power sensors update correctly in HA?
    Run Keyword If    '${status}' != 'SKIP'
    ...    Should Be Equal    ${status}    PASS    Power state change not reflected in HA

    # Collect final data
    Print Test Step    Final verification:\n- Check sensor history graphs\n- Verify all transitions were recorded\n- Note any missing or incorrect data

    ${status}=    Get User Verification    Are all battery/power sensors working correctly?
    Should Not Be Equal    ${status}    FAIL    Battery/power sensor issues detected

    # Collect diagnostics
    Collect HA Sensor Data    03_final_battery_data

Low Battery Alert Test
    [Documentation]    Test low battery threshold alerts (requires laptop)
    [Tags]    battery    manual    laptop

    Print Test Step    Check if this test is applicable:\n- This test requires a laptop with battery\n- Current battery level should be above 20%\n- You need to be able to simulate low battery

    ${applicable}=    Get Yes No    Do you have a laptop with battery that can test low battery scenarios?

    Run Keyword If    not ${applicable}
    ...    Skip    Test not applicable to this system

    # Continue with test steps...
    Log    Low battery test to be implemented

*** Keywords ***
Suite Setup
    [Documentation]    One-time setup for battery test suite
    Log    Starting battery test suite
    # HA token is required - will fail early if not provided
    Verify Home Assistant Available

Suite Teardown
    [Documentation]    One-time cleanup for battery test suite
    Log    Battery test suite completed
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
