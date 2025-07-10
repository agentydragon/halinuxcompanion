*** Settings ***
Documentation     Very simple prompt test
Library           BuiltIn

*** Test Cases ***
Test Simple Prompt
    [Documentation]    Test basic Robot prompt

    Log To Console    \n\n${'='*60}
    Log To Console    MANUAL INPUT REQUIRED
    Log To Console    ${'='*60}

    ${user_input}=    Pause Execution    Please type YES or NO and press Enter to continue

    Log To Console    \nYou entered: ${user_input}

    Should Not Be Empty    ${user_input}    No input received
