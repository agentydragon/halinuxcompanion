import asyncio
import json
import logging
import platform
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
from pydantic import BaseModel, ConfigDict, Field
from xdg_base_dirs import xdg_state_home

from .constants import DEFAULT_NOTIFIER_PORT, SC_INTEGRATION_DELETED, SC_OK
from .hardware_config import HardwareConfig
from .models import RegistrationData
from .secret_storage import SecretStorageBackend

if TYPE_CHECKING:
    from halinuxcompanion.api import API


def get_state_dir() -> Path:
    """Get the state directory path using XDG_STATE_HOME."""
    return Path(xdg_state_home() / "halinuxcompanion")


class CommandConfig(BaseModel):
    name: str
    command: list[str]


class NotificationServiceConfig(BaseModel):
    enabled: bool
    url_program: str
    commands: dict[str, CommandConfig] = Field(default_factory=dict)


class ServicesConfig(BaseModel):
    notifications: NotificationServiceConfig


class CompanionConfig(BaseModel):
    ha_url: str
    ha_token: str | None = None
    device_id: str
    device_name: str | None
    manufacturer: str | None
    model: str | None
    # HTTP listener configuration for both OAuth and notifications
    http_port: int = Field(default=DEFAULT_NOTIFIER_PORT, alias="notifier_listen_port")
    http_host: str = Field(alias="notifier_listen_address")
    refresh_interval: int = 15
    hardware: HardwareConfig
    services: ServicesConfig
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

    def __init__(self, state_dir: Path | None = None):
        """Initialize state manager.

        Args:
            state_dir: Directory to store state file. Defaults to XDG state home.
        """
        self._state_dir = state_dir or get_state_dir()
        self._state_path = self._state_dir / "state.json"
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
                return StateData.model_validate(data)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, ValueError):
            logger.exception("Error loading state file, starting fresh")
            return StateData()

    def _save(self) -> None:
        """Save state data to file."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(self._data.model_dump_json(indent=2))
        logger.debug(f"State saved to {self._state_path}")


class Companion:
    """Class encolsing a companion instance
    https://developers.home-assistant.io/docs/api/native-app-integration/setup
    """

    # TODO: This class is just a huge pile of things
    # TODO: Get the default values from something that helps sets releases.
    app_name: str = "Linux Companion"
    app_version: str = "0.0.1"
    config: CompanionConfig
    # TODO: Encryption requires https://github.com/jedisct1/libsodium

    @property
    def app_id(self) -> str:
        """Get the unique application ID."""
        return f"halinuxcompanion-{self.app_version}"

    state: State

    @property
    def http_port(self) -> int:
        """Get the port for the local HTTP listener (notifications and OAuth)."""
        return self.config.http_port

    @property
    def http_host(self) -> str:
        """Get the host/IP address for the local HTTP listener."""
        return self.config.http_host

    @property
    def hardware(self) -> HardwareConfig:
        return self.config.hardware

    @property
    def ha_token(self) -> str | None:
        return self.config.ha_token

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
    def notifier(self) -> bool:
        """Check if the notifier service is enabled."""
        # Push token will be generated/loaded in load_or_register
        return self.config.services.notifications.enabled

    def __init__(self, config: CompanionConfig):
        # Load only allowed values
        self.config = config
        self.state = State()

    @property
    def device_name(self) -> str:
        """Get the name of the device."""
        return self.config.device_name or platform.node()

    async def register(self, api: "API"):
        """Register the companion with Home Assistant with retry logic.

        :param api: API instance for communication
        :param max_retries: Maximum number of registration attempts
        :return: registration_data if successful
        :raises: Exception if registration fails after all retries
        """
        app_data = {}
        if push_token := self.load_or_generate_push_token():
            app_data = {
                "push_token": push_token,
                "push_url": f"http://{self.http_host}:{self.http_port}/notify",
            }
        payload = {
            "device_id": self.device_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "device_name": self.device_name,
            "manufacturer": self.config.manufacturer or platform.system(),
            "model": self.config.model or "Computer",
            "os_name": platform.system(),
            "os_version": platform.release(),
            "supports_encryption": False,
            "app_data": app_data,
        }

        logger.info(f"Registering companion device with payload: {payload=}")

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
        if self.state.push_token:
            logger.info("Loaded existing push token")
            return self.state.push_token

        logger.info("Generating new push token")
        self.state.push_token = secrets.token_urlsafe(32)
        # State is automatically saved when properties are set
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
            res = await api.webhook_post({"type": "get_config"})
            if res.status == SC_OK:
                return self.state.registration_data
            if res.status != SC_INTEGRATION_DELETED:
                raise RuntimeError(f"Failed to get config via webhook {res.status=}")

        logger.info("Registration data not found or needing re-registration, registering device")
        return await self.register(api)  # type: ignore[no-any-return]
