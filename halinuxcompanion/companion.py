import asyncio
import json
import logging
import platform
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

import aiohttp
from pydantic import BaseModel, ConfigDict, Field
from xdg_base_dirs import xdg_state_home

from .hardware_config import HardwareConfig
from .models import RegistrationData
from .secrets import SecretStorageBackend

SC_INTEGRATION_DELETED = 410

if TYPE_CHECKING:
    from halinuxcompanion.api import API


def get_state_dir() -> Path:
    """Get the state directory path using XDG_STATE_HOME."""
    return xdg_state_home() / "halinuxcompanion"


class CommandConfig(BaseModel):
    name: str
    command: List[str]


class NotificationServiceConfig(BaseModel):
    enabled: bool
    url_program: str
    commands: Dict[str, CommandConfig] = Field(default_factory=dict)


class ServicesConfig(BaseModel):
    notifications: NotificationServiceConfig


class CompanionConfig(BaseModel):
    ha_url: str
    ha_token: str | None = None
    device_id: str
    device_name: str | None
    manufacturer: str | None
    model: str | None
    computer_port: int = 8400
    computer_ip: str
    refresh_interval: int = 15
    hardware: HardwareConfig
    services: ServicesConfig
    storage_backend: SecretStorageBackend = Field(
        default=SecretStorageBackend.LIBSECRET,
        description="Storage backend for secrets",
    )
    loglevel: str | None = None


logger = logging.getLogger("halinuxcompanion")


class State(BaseModel):
    """State class to hold the companion state.

    This class is used to store the companion state in a file.
    It is used to store the push token and other state information.
    """

    model_config = ConfigDict(extra="forbid")

    push_token: str | None = None
    registration_data: RegistrationData | None = None


def state_path() -> Path:
    """Get the state file path."""
    return get_state_dir() / "state.json"


def load_state() -> State:
    """Load state data including push token."""
    if not state_path().exists():
        return State()
    with open(state_path()) as f:
        return State.model_validate(json.load(f))


def save_state(state):
    """Save state data including push token."""
    state_path().parent.mkdir(parents=True, exist_ok=True)
    state_path().write_text(State.model_dump_json(state, indent=2))


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
    def computer_port(self) -> int:
        """Get the port for the companion computer service."""
        return self.config.computer_port

    @property
    def computer_ip(self) -> str:
        """Get the IP address of the companion computer service."""
        return self.config.computer_ip

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
        self.state = load_state()

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
                "push_url": f"http://{self.computer_ip}:{self.computer_port}/notify",
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
                raise Exception(
                    f"Device registration failed with {res.status}: {await res.text()}"
                )
        except (aiohttp.ClientError, asyncio.TimeoutError):
            logger.error("Device registration failed")
            raise

        registration_data = RegistrationData.model_validate(await res.json())
        logger.info(f"Device registration successful: {registration_data}")

        self.state.registration_data = registration_data
        save_state(self.state)

        return registration_data

    def load_or_generate_push_token(self) -> str:
        if self.state.push_token:
            logger.info("Loaded existing push token")
            return self.state.push_token

        logger.info("Generating new push token")
        self.state.push_token = secrets.token_urlsafe(32)
        save_state(self.state)
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
            res = await api.webhook_post("get_config", data={"type": "get_config"})
            if res.status == 200:
                return self.state.registration_data
            if res.status != SC_INTEGRATION_DELETED:
                raise Exception(f"Failed to get config via webhook {res.status=}")

        logger.info(
            "Registration data not found or needing re-registration, registering device"
        )
        return await self.register(api)
