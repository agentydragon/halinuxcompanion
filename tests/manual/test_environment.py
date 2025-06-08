"""Test environment manager for manual testing."""

from pathlib import Path
from typing import Any

from HACompanionLibrary import HACompanionLibrary, HAConnection


class TestEnvironment:
    """Manages the test environment including Home Assistant setup."""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.ha_library = HACompanionLibrary()
        self._docker_context: Any = None
        self.ha_connection: HAConnection | None = None

    async def setup(self) -> None:
        """Set up the test environment."""
        self._docker_context = self.ha_library.home_assistant_docker()
        self.ha_connection = self._docker_context.__enter__()

    async def cleanup(self) -> None:
        """Clean up the test environment."""
        if self._docker_context:
            self._docker_context.__exit__(None, None, None)

    def is_ha_available(self) -> bool:
        """Check if Home Assistant is available."""
        if self.ha_connection:
            return self.ha_connection.is_alive()
        return False
