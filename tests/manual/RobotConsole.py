"""Alternative console interaction for Robot Framework using BuiltIn pause."""

from robot.libraries.BuiltIn import BuiltIn


class RobotConsole:
    """Console interaction that works with Robot Framework's execution model."""

    def get_user_response_with_pause(self, prompt, options):
        """Get user response by pausing execution and asking for input.

        This uses Robot's Pause Execution to properly handle stdin.
        """
        builtin = BuiltIn()

        # Build the full prompt message
        message = f"\n{prompt}\n{'-' * len(prompt)}\n"

        if options == ["yes", "no", "skip"]:
            message += "  [Y] Yes\n  [N] No\n  [S] Skip\n\n"
            message += "Please enter Y/N/S and press Enter when Robot resumes:"

            # Log the prompt
            builtin.log_to_console(message)

            # Pause and let user enter response
            user_input = builtin.pause_execution(
                "Enter your choice (Y/N/S) in the terminal and press Enter to continue"
            )

            # The pause returns whatever the user typed
            if user_input:
                choice = user_input.strip().upper()
                if choice in ["Y", "YES"]:
                    return "yes"
                if choice in ["N", "NO"]:
                    return "no"
                if choice in ["S", "SKIP"]:
                    return "skip"

            # Default to skip if invalid
            builtin.log_to_console("Invalid input, defaulting to 'skip'")
            return "skip"

        # For other option lists
        for i, option in enumerate(options, 1):
            message += f"  [{i}] {option}\n"

        message += f"\nPlease enter 1-{len(options)} and press Enter when Robot resumes:"
        builtin.log_to_console(message)

        user_input = builtin.pause_execution(
            f"Enter your choice (1-{len(options)}) in the terminal and press Enter to continue"
        )

        if user_input and user_input.strip().isdigit():
            choice = int(user_input.strip())
            if 1 <= choice <= len(options):
                return options[choice - 1]

        # Default to first option
        builtin.log_to_console(f"Invalid input, defaulting to '{options[0]}'")
        return options[0]
