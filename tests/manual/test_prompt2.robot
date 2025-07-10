*** Settings ***
Documentation     Test Robot's built-in dialog capabilities
Library           Dialogs

*** Test Cases ***
Test Built-in Dialog
    [Documentation]    Test Robot's built-in dialog

    Log To Console    \n\n=== TESTING BUILT-IN DIALOG ===

    ${response}=    Get Selection From User    Is halinuxcompanion running?    Yes    No    Skip

    Log To Console    You selected: ${response}
