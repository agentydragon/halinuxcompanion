*** Settings ***
Documentation     Simple test to debug console prompts
Library           ./ConsoleMenu.py

*** Test Cases ***
Test Console Prompt
    [Documentation]    Test if console prompts are working

    Log To Console    \n\n=== STARTING PROMPT TEST ===
    Log To Console    This should show a Y/N/S prompt below:

    ${response}=    Get Yes No Skip    Can you see this prompt?

    Log To Console    You selected: ${response}

    Should Not Be Empty    ${response}    No response received from prompt

Test Direct Menu
    [Documentation]    Test menu selection

    Log To Console    \n\n=== TESTING MENU ===

    ${selection}=    Get Menu Selection    Choose an option    Option A    Option B    Option C

    Log To Console    You selected option: ${selection}
