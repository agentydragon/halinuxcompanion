"""Helper functions for HA testing in Robot Framework."""

import requests
from robot.api import logger


class HATestHelper:
    """Helper class for Home Assistant testing."""

    def verify_ha_with_token(self, ha_url: str, token: str) -> bool:
        """Verify HA is accessible with the given token."""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(f"{ha_url}/api/", headers=headers, timeout=5)
            logger.info(f"HA API response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to verify HA: {e}")
            return False
