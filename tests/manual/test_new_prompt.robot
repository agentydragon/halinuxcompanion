*** Settings ***
Documentation     Test the new prompt mechanism
Resource          HALinuxCompanionLibrary.robot

*** Test Cases ***
Test New User Verification
    [Documentation]    Test the new prompt system

    ${status}=    Get User Verification    Can you see this prompt clearly?

    Log To Console    You responded: ${status}

Test Pause For Action
    [Documentation]    Test pause for action

    Pause For Action    Please open a new terminal window

    Log To Console    Action completed!
