import asyncio
import json
import logging
import platform
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
from pydantic import BaseModel, ConfigDict, Field

from .constants import DEFAULT_NOTIFIER_PORT, SC_INTEGRATION_DELETED, SC_OK
from .models import RegistrationData
from .module_config import ModulesConfig
from .paths import get_state_file_path
from .secret_storage import SecretStorageBackend

if TYPE_CHECKING:
    from halinuxcompanion.api import API


class CommandConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    command: list[str]


class NotificationServiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    url_program: str
    commands: dict[str, CommandConfig] = Field(default_factory=dict)


class CompanionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ha_url: str
    ha_token: str | None = None
    device_id: str
    device_name: str | None
    manufacturer: str | None
    model: str | None
    # Local HTTP listener configuration for OAuth callbacks and push notifications
    local_http_port: int = Field(default=DEFAULT_NOTIFIER_PORT)
    local_http_host: str
    refresh_interval: int = 15
    hardware: ModulesConfig
    notifications: NotificationServiceConfig
    storage_backend: SecretStorageBackend = Field(
        default=SecretStorageBackend.LIBSECRET,
        description="Storage backend for secrets",
    )
    loglevel: str | None = None


logger = logging.getLogger("halinuxcompanion")


class StateData(BaseModel):
    """Data model for companion state."""

    model_config = ConfigDict(extra="forbid")

    push_token: str | None = None
    registration_data: RegistrationData | None = None


class State:
    """Manages persistent companion state.

    This class handles loading and saving companion state data
    including push tokens and registration information.
    """

    def __init__(self):
        """Initialize state manager."""
        self._state_path = get_state_file_path()
        self._data = self._load()

    @property
    def path(self) -> Path:
        """Get the state file path."""
        return self._state_path

    @property
    def push_token(self) -> str | None:
        """Get the push token."""
        return self._data.push_token

    @push_token.setter
    def push_token(self, value: str | None) -> None:
        """Set the push token."""
        self._data.push_token = value
        self._save()

    @property
    def registration_data(self) -> RegistrationData | None:
        """Get the registration data."""
        return self._data.registration_data

    @registration_data.setter
    def registration_data(self, value: RegistrationData | None) -> None:
        """Set the registration data."""
        self._data.registration_data = value
        self._save()

    def _load(self) -> StateData:
        """Load state data from file."""
        if not self._state_path.exists():
            return StateData()

        try:
            with open(self._state_path) as f:
                data = json.load(f)
                return StateData.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            logger.exception("Error loading state file, starting fresh")
            return StateData()

    def _save(self) -> None:
        """Save state data to file."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(self._data.model_dump_json(indent=2))
        logger.debug(f"State saved to {self._state_path}")


@dataclass
class Companion:
    """Class encolsing a companion instance
    https://developers.home-assistant.io/docs/api/native-app-integration/setup
    """

    # TODO: This class is just a huge pile of things
    # TODO: Get the default values from something that helps sets releases.
    config: CompanionConfig
    app_name: str = "Linux Companion"
    state: State = field(default_factory=State)
    # TODO: Encryption requires https://github.com/jedisct1/libsodium

    @property
    def app_id(self) -> str:
        """Get the unique application ID."""
        return f"halinuxcompanion-{self.companion_version}"

    @property
    def http_host(self) -> str:
        """Get the host/IP address for the local HTTP listener."""
        return self.config.local_http_host

    @property
    def http_port(self) -> int:
        """Get the port for the local HTTP listener (notifications and OAuth)."""
        return self.config.local_http_port

    @property
    def refresh_interval(self) -> int:
        """Get the refresh interval in seconds."""
        return self.config.refresh_interval

    @property
    def ha_url(self) -> str:
        """Get the base URL for Home Assistant."""
        return self.config.ha_url.rstrip("/")

    @property
    def device_id(self) -> str:
        """Get the unique device ID."""
        # TODO: Revisit this device_id which must be unique, used for notification events
        return self.config.device_id or platform.node()

    @property
    def device_name(self) -> str:
        """Get the name of the device."""
        return self.config.device_name or platform.node()

    @property
    def companion_version(self) -> str:
        """Get the companion version."""
        return "0.1.0"

    async def register(self, api: "API"):
        """Register the companion with Home Assistant with retry logic.

        :param api: API instance for communication
        :param max_retries: Maximum number of registration attempts
        :return: registration_data if successful
        :raises: Exception if registration fails after all retries
        """
        push_token = self.load_or_generate_push_token()
        app_data = {
            "push_token": push_token,
            "push_url": f"http://{self.http_host}:{self.http_port}/notify",
        }
        payload = {
            "device_id": self.device_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "app_version": self.companion_version,
            "device_name": self.device_name,
            "manufacturer": self.config.manufacturer or platform.system(),
            "model": self.config.model or "Computer",
            "os_name": platform.system(),
            "os_version": platform.release(),
            "supports_encryption": False,
            "app_data": app_data,
        }

        try:
            res = await api.post("/api/mobile_app/registrations", json=payload)
            if not res.ok:
                raise RuntimeError(f"Device registration failed with {res.status}: {await res.text()}")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            logger.exception("Device registration failed")
            raise

        registration_data = RegistrationData.model_validate(await res.json())
        logger.info(f"Device registration successful: {registration_data}")

        self.state.registration_data = registration_data
        # State is automatically saved when properties are set

        return registration_data

    def load_or_generate_push_token(self) -> str:
        if not self.state.push_token:
            logger.info("Generating new push token")
            self.state.push_token = secrets.token_urlsafe(32)
        return self.state.push_token

    async def load_or_register(self, api: "API") -> RegistrationData:
        """
        Load registration data from disk or register the companion APP

        :return: registration_data
        """

        """Check if current registration is still valid"""
        logger.info("Checking if device is already registered")
        if self.state.registration_data:
            api.registration = self.state.registration_data
            res = await api.webhook_post({"type": "get_config", "data": {}})
            if res.status == SC_OK:
                return self.state.registration_data
            if res.status != SC_INTEGRATION_DELETED:
                raise RuntimeError(f"Failed to get config via webhook {res.status=}")

        logger.info("Registration data not found or needing re-registration, registering device")
        return await self.register(api)  # type: ignore[no-any-return]
