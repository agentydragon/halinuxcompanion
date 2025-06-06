"""Home Assistant Mobile App API client."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import aiohttp

from halinuxcompanion.constants import WEBHOOK_TIMEOUT
from halinuxcompanion.modules.base import SensorRegistration, SensorUpdate

from .models import Registration

logger = logging.getLogger(__name__)


class MobileAppClient:
    """Client for Home Assistant Mobile App API."""

    def __init__(self, registration: Registration, session: aiohttp.ClientSession):
        """Initialize the client.

        Args:
            registration: The registration data from Home Assistant.
            session: The aiohttp session to use for requests.
        """
        self.registration = registration
        self.session = session

    @property
    def webhook_url(self) -> str:
        """Get the webhook URL."""
        return f"{self.registration.instance_url}/api/webhook/{self.registration.webhook_id}"

    async def register_sensors(self, sensors: list[SensorRegistration]) -> None:
        """Register all sensors with Home Assistant.

        Args:
            sensors: List of sensors to register.
        """
        # Send registration for each sensor
        await asyncio.gather(
            *[
                self._post_webhook("register_sensor", sensor.model_dump(exclude_none=True, by_alias=True))
                for sensor in sensors
            ]
        )

        logger.info(f"Registered {len(sensors)} sensors with Home Assistant")

    async def update_sensors(self, updates: list[SensorUpdate]) -> None:
        """Send batched sensor updates.

        Args:
            updates: List of sensor updates to send.

        Note: SensorUpdate is designed to map 1:1 to the API format.
        """
        await self._post_webhook("update_sensor_states", [update.model_dump(exclude_none=True) for update in updates])

        # Log the actual updates for debugging
        for update in updates:
            logger.debug(f"Sensor update: {update.unique_id} = {update.state} (icon: {update.icon})")
        logger.info(f"Sent {len(updates)} sensor updates")

    async def _post_webhook(self, webhook_type: str, data: Any) -> None:
        """Post data to webhook endpoint.

        Args:
            webhook_type: The type of webhook message.
            data: The data to send in the webhook.

        Raises:
            aiohttp.ClientError: If the request fails.
        """
        async with self.session.post(
            self.webhook_url,
            json={"type": webhook_type, "data": data},
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=WEBHOOK_TIMEOUT.total_seconds()),
        ) as resp:
            resp.raise_for_status()
            logger.debug(f"Webhook POST successful: {webhook_type}")


@asynccontextmanager
async def create_api_client(registration: Registration):
    """Create an API client with managed session.

    Args:
        registration: The registration data from Home Assistant.

    Yields:
        MobileAppClient: The configured API client.
    """
    async with aiohttp.ClientSession() as session:
        yield MobileAppClient(registration, session)
