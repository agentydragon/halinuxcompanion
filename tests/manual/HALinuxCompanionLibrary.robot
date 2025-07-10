*** Settings ***
Documentation     Robot Framework resource file for Home Assistant Linux Companion testing
...               This provides keywords for testing halinuxcompanion with Home Assistant
Library           OperatingSystem
Library           Process
Library           DateTime
Library           Collections
Library           String
Library           RequestsLibrary
Library           ./python_implementation/HACompanionLibrary.py    WITH NAME    HALib
Library           ./HATestHelper.py

*** Variables ***
${HA_URL}                 http://localhost:8123
${HA_TOKEN}               ${EMPTY}    # REQUIRED - will be set by command line
${HALINUXCOMPANION_PID}   ${NONE}
${TEST_START_TIME}        ${NONE}
${RESULTS_DIR}            ${NONE}

*** Keywords ***
Setup Test Environment
    [Documentation]    Initialize test environment and directories
    [Arguments]    ${test_name}

    # Verify HA token is provided
    Should Not Be Empty    ${HA_TOKEN}    HA_TOKEN is required. Run with --variable HA_TOKEN:your_token

    ${timestamp}=    Get Current Date    result_format=%Y%m%d_%H%M%S
    ${results_dir}=    Set Variable    ${CURDIR}/manual_test_results/${test_name}_${timestamp}
    Create Directory    ${results_dir}
    Set Suite Variable    ${RESULTS_DIR}    ${results_dir}
    Set Suite Variable    ${TEST_START_TIME}    ${timestamp}

    # Initialize Python library with token
    Set Test Variable    ${HALib.ha_token}    ${HA_TOKEN}
    Set Test Variable    ${HALib.ha_url}    ${HA_URL}

    Log    Test results will be saved to: ${results_dir}
    RETURN    ${results_dir}

Verify Home Assistant Available
    [Documentation]    Check if Home Assistant is running and accessible with valid token
    # Token is required
    Should Not Be Empty    ${HA_TOKEN}    HA_TOKEN is required

    # Use Python helper to verify HA
    ${available}=    Verify HA With Token    ${HA_URL}    ${HA_TOKEN}

    Should Be True    ${available}    Home Assistant not accessible at ${HA_URL} with provided token
    RETURN    ${available}

Start HALinuxCompanion
    [Documentation]    Start halinuxcompanion with debug logging
    [Arguments]    ${log_file}=${RESULTS_DIR}/halinuxcompanion.log

    # Ensure any existing instance is stopped
    Run Keyword If    '${HALINUXCOMPANION_PID}' != '${NONE}'
    ...    Stop HALinuxCompanion

    # Start with logging
    ${handle}=    Start Process    halinuxcompanion    --debug    run
    ...    stdout=${log_file}
    ...    stderr=STDOUT
    ...    env:DBUS_VERBOSE=1
    ...    env:PYTHONUNBUFFERED=1

    Sleep    3s    Wait for startup

    # Verify it's running
    ${is_running}=    Is Process Running    ${handle}
    Run Keyword If    not ${is_running}
    ...    Fail    halinuxcompanion failed to start

    ${pid}=    Get Process Id    ${handle}
    Set Suite Variable    ${HALINUXCOMPANION_PID}    ${handle}
    Log    Started halinuxcompanion with PID: ${pid}
    RETURN    ${pid}

Stop HALinuxCompanion
    [Documentation]    Stop halinuxcompanion gracefully
    # Check if PID is None without string comparison
    ${is_none}=    Run Keyword And Return Status    Should Be Equal    ${HALINUXCOMPANION_PID}    ${NONE}
    Run Keyword If    ${is_none}    Return From Keyword

    ${result}=    Terminate Process    ${HALINUXCOMPANION_PID}    kill=True
    Set Suite Variable    ${HALINUXCOMPANION_PID}    ${NONE}
    Log    halinuxcompanion stopped

Collect DBus Diagnostics
    [Documentation]    Collect DBus diagnostic information
    [Arguments]    ${prefix}
    ${diag_dir}=    Set Variable    ${RESULTS_DIR}/${prefix}_dbus_diagnostics
    Create Directory    ${diag_dir}

    # Define diagnostic commands
    @{commands}=    Create List
    ...    busctl tree org.bluez
    ...    busctl introspect org.bluez /org/bluez
    ...    systemctl status bluetooth
    ...    rfkill list
    ...    bluetoothctl show
    ...    bluetoothctl devices

    # Run each command and save output
    FOR    ${cmd}    IN    @{commands}
        ${rc}    ${output}=    Run And Return Rc And Output    ${cmd}
        ${cmd_file}=    Replace String    ${cmd}    ${SPACE}    _
        Create File    ${diag_dir}/${cmd_file}.txt    Command: ${cmd}\nReturn Code: ${rc}\n${\n}${output}
        Log    Executed: ${cmd} (RC: ${rc})    DEBUG
    END

    # Create summary file with Robot's native logging
    ${timestamp}=    Get Current Date
    ${summary}=    Catenate    SEPARATOR=\n
    ...    DBus Diagnostics Summary
    ...    =======================
    ...    Timestamp: ${timestamp}
    ...    Directory: ${diag_dir}
    ...    Commands executed: ${commands.__len__()}

    Create File    ${diag_dir}/summary.txt    ${summary}
    Log    DBus diagnostics collected    console=True

Take Screenshot
    [Documentation]    Take a desktop screenshot
    [Arguments]    ${name}
    ${screenshot_path}=    Set Variable    ${RESULTS_DIR}/${name}.png

    # Try different screenshot tools
    ${tools}=    Create List
    ...    gnome-screenshot -f ${screenshot_path}
    ...    scrot ${screenshot_path}
    ...    import -window root ${screenshot_path}

    FOR    ${tool}    IN    @{tools}
        ${rc}=    Run Keyword And Return Status    Run    ${tool}
        Run Keyword If    ${rc}    Exit For Loop
    END

    ${exists}=    File Should Exist    ${screenshot_path}
    Run Keyword If    ${exists}    Log    Screenshot saved: ${screenshot_path}
    ...    ELSE    Log    WARNING: No screenshot tool available

Mark Test Start Time
    [Documentation]    Mark the start time for HA history collection
    ${start_time}=    Get Current Date    result_format=%Y-%m-%dT%H:%M:%S.000Z
    Set Suite Variable    ${TEST_START_TIME}    ${start_time}
    HALib.Mark Test Start
    Log    Test start time marked: ${start_time}

Collect HA Sensor Data
    [Documentation]    Collect sensor data from Home Assistant
    [Arguments]    ${prefix}
    # Token is required - no conditional handling
    HALib.Collect Ha Sensor Data    ${RESULTS_DIR}    ${prefix}

Get User Verification
    [Documentation]    Get manual verification from user
    [Arguments]    ${prompt}

    # Display the prompt clearly
    Log To Console    ${EMPTY}
    Log To Console    ========================================
    Log To Console    ${prompt}
    Log To Console    ----------------------------------------
    Log To Console    Options:
    Log To Console    - Type 'y' or 'yes' for YES
    Log To Console    - Type 'n' or 'no' for NO
    Log To Console    - Type 's' or 'skip' to SKIP
    Log To Console    ========================================

    # Use Robot's Pause Execution which properly handles input
    ${user_input}=    Pause Execution    Enter your choice (y/n/s) and press Enter to continue

    # Process the response
    ${response}=    Set Variable    skip
    ${lower_input}=    Convert To Lower Case    ${user_input}
    Run Keyword If    '${lower_input}' in ['y', 'yes']    Set Variable    ${response}    yes
    Run Keyword If    '${lower_input}' in ['n', 'no']     Set Variable    ${response}    no
    Run Keyword If    '${lower_input}' in ['s', 'skip']   Set Variable    ${response}    skip

    # Actually set the response variable properly
    ${response}=    Run Keyword If    '${lower_input}' in ['y', 'yes']    Set Variable    yes
    ...    ELSE IF    '${lower_input}' in ['n', 'no']    Set Variable    no
    ...    ELSE    Set Variable    skip

    # Log result immediately
    Run Keyword If    '${response}' == 'yes'
    ...    Log    ✓ User verified: ${prompt}    console=True
    ...    ELSE IF    '${response}' == 'no'
    ...    Log    ✗ User reported issue: ${prompt}    WARN    console=True
    ...    ELSE
    ...    Log    ⊘ User skipped: ${prompt}    console=True

    # Return simple status
    ${status}=    Set Variable If
    ...    '${response}' == 'yes'    PASS
    ...    '${response}' == 'no'    FAIL
    ...    SKIP

    RETURN    ${status}

Pause For Action
    [Documentation]    Pause and wait for user to complete an action
    [Arguments]    ${message}
    Log To Console    ${EMPTY}
    Log To Console    ****************************************
    Log To Console    ACTION REQUIRED:
    Log To Console    ${message}
    Log To Console    ****************************************
    Pause Execution    Press Enter when you have completed the action

Print Test Step
    [Documentation]    Print a formatted test step
    [Arguments]    ${instruction}
    Log To Console    ${\n}---
    Log To Console    ${instruction}
    Log To Console    ---${\n}

Check Bluetooth Status
    [Documentation]    Automatically check if Bluetooth is on or off using rfkill
    ${output}=    Run    rfkill list bluetooth
    ${is_blocked}=    Run Keyword And Return Status    Should Contain    ${output}    blocked
    ${status}=    Set Variable If    ${is_blocked}    off    on
    Log To Console    Bluetooth status detected: ${status}
    RETURN    ${status}

Verify Bluetooth Is Off
    [Documentation]    Verify Bluetooth is off, automatically or with user confirmation
    ${auto_status}=    Check Bluetooth Status

    # If rfkill shows bluetooth is blocked (off), auto-accept
    Run Keyword If    '${auto_status}' == 'off'
    ...    Run Keywords
    ...    Log To Console    ✓ Bluetooth is OFF (auto-verified via rfkill)
    ...    AND    Return From Keyword    ${True}

    # Otherwise ask user
    Log To Console    ⚠ Bluetooth appears to be ON according to rfkill
    ${status}=    Get User Verification    Is Bluetooth actually OFF?
    ${verified}=    Set Variable If    '${status}' == 'PASS'    ${True}    ${False}
    RETURN    ${verified}

Verify Bluetooth Is On
    [Documentation]    Verify Bluetooth is on, automatically or with user confirmation
    ${auto_status}=    Check Bluetooth Status

    # If rfkill shows bluetooth is not blocked (on), auto-accept
    Run Keyword If    '${auto_status}' == 'on'
    ...    Run Keywords
    ...    Log To Console    ✓ Bluetooth is ON (auto-verified via rfkill)
    ...    AND    Return From Keyword    ${True}

    # Otherwise ask user
    Log To Console    ⚠ Bluetooth appears to be OFF according to rfkill
    ${status}=    Get User Verification    Is Bluetooth actually ON?
    ${verified}=    Set Variable If    '${status}' == 'PASS'    ${True}    ${False}
    RETURN    ${verified}

# Removed Generate Test Report - using Robot's native reporting instead
