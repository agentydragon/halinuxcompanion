"""Console menu library for Robot Framework manual tests."""

import sys


class ConsoleMenu:
    """Library for console-based user interaction in Robot tests."""

    def __init__(self):
        """Initialize the console menu."""
        # Check if we have a proper TTY
        self.has_tty = sys.stdin.isatty()
        self.tty = None

        if not self.has_tty:
            # Try to reopen stdin from /dev/tty if available
            try:
                self.tty = open("/dev/tty")
            except OSError:
                # Try regular stdin as fallback
                self.tty = None

    def _get_input(self, prompt=""):
        """Get input, handling non-TTY environments."""
        if self.has_tty:
            return input(prompt)
        if self.tty:
            # Use the direct TTY
            if prompt:
                print(prompt, end="", flush=True)
            return self.tty.readline().strip()
        # Last resort - try regular input anyway
        # This might work if stdin is connected but not a TTY
        try:
            return input(prompt)
        except EOFError:
            raise RuntimeError("No input available - stdin is not connected")

    def get_menu_selection(self, prompt, *options):
        """Display a menu and get user selection.

        Args:
            prompt: The question to ask
            *options: Variable number of menu options

        Returns:
            The selected option text
        """
        print(f"\n{prompt}")
        print("-" * len(prompt))

        # Display options with numbers
        for i, option in enumerate(options, 1):
            print(f"  [{i}] {option}")

        # Get valid selection
        while True:
            print(f"\nEnter your choice [1-{len(options)}]: ", end="", flush=True)
            try:
                choice = int(self._get_input().strip())
                if 1 <= choice <= len(options):
                    selected = options[choice - 1]
                    print(f"Selected: {selected}\n")
                    return selected
                print(f"Invalid choice. Enter a number between 1 and {len(options)}.")
            except ValueError:
                print(f"Invalid input. Enter a number between 1 and {len(options)}.")

    def get_yes_no_skip(self, prompt):
        """Get yes/no/skip response with clear options.

        Returns: 'yes', 'no', or 'skip'
        """
        print(f"\n{prompt}")
        print("-" * len(prompt))
        print("  [Y] Yes")
        print("  [N] No")
        print("  [S] Skip")
        sys.stdout.flush()  # Force flush output

        while True:
            print("\nYour choice [Y/N/S]: ", end="", flush=True)
            sys.stdout.flush()  # Force flush before input
            choice = self._get_input().strip().upper()
            if choice in ["Y", "YES"]:
                print("Selected: Yes\n")
                return "yes"
            if choice in ["N", "NO"]:
                print("Selected: No\n")
                return "no"
            if choice in ["S", "SKIP"]:
                print("Selected: Skip\n")
                return "skip"
            print("Invalid choice. Please enter Y, N, or S.")

    def get_yes_no(self, prompt):
        """Get yes/no response.

        Returns: True for yes, False for no
        """
        print(f"\n{prompt}")
        print("-" * len(prompt))
        print("  [Y] Yes")
        print("  [N] No")
        sys.stdout.flush()  # Force flush output

        while True:
            print("\nYour choice [Y/N]: ", end="", flush=True)
            sys.stdout.flush()  # Force flush before input
            choice = self._get_input().strip().upper()
            if choice in ["Y", "YES"]:
                print("Selected: Yes\n")
                return True
            if choice in ["N", "NO"]:
                print("Selected: No\n")
                return False
            print("Invalid choice. Please enter Y or N.")

    def get_text_input(self, prompt):
        """Get free text input from user."""
        print(f"\n{prompt}")
        print("-" * len(prompt))
        print("Enter your response (or press Enter to skip): ", end="", flush=True)
        response = self._get_input().strip()
        if response:
            print(f"Entered: {response}\n")
        else:
            print("(No response entered)\n")
        return response

    def pause_for_action(self, message):
        """Pause and wait for user to complete an action."""
        print("!" * 60)
        print(f"ACTION REQUIRED: {message}")
        print("!" * 60)
        print("\nPress Enter when done...", end="", flush=True)
        self._get_input()
        print("Continuing...\n")
