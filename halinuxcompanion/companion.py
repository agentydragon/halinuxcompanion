import os
import json
import platform
import uuid
import logging
import secrets
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from xdg_base_dirs import xdg_state_home

import aiohttp

SC_INTEGRATION_DELETED = 410

if TYPE_CHECKING:
    from halinuxcompanion.api import API


def get_state_dir() -> Path:
    """Get the state directory path using XDG_STATE_HOME."""
    return xdg_state_home() / "halinuxcompanion"

CONFIG_KEYS = [
    ("ha_url", True),
    ("ha_token", False),  # Now optional - can use OAuth instead
    ("device_id", True),
    ("device_name", False),
    ("manufacturer", False),
    ("model", False),
    ("computer_ip", True),
    ("computer_port", True),
    ("refresh_interval", False),
    ("services", True),
    ("sensors", True),
]


class CommandConfig(BaseModel):
    name: str
    command: List[str]


class NotificationServiceConfig(BaseModel):
    enabled: bool
    url_program: str
    commands: Dict[str, CommandConfig] = Field(default_factory=dict)


class ServicesConfig(BaseModel):
    notifications: Optional[NotificationServiceConfig]


class SensorConfig(BaseModel):
    enabled: bool
    name: Optional[str] = None


class CompanionConfig(BaseModel):
    ha_url: str
    ha_token: Optional[str] = None
    device_id: str
    device_name: Optional[str]
    manufacturer: Optional[str]
    model: Optional[str]
    computer_ip: str
    computer_port: int
    refresh_interval: Optional[int]
    sensors: Dict[str, SensorConfig]
    services: Optional[ServicesConfig]
    storage_backend: Optional[str] = "auto"  # "file", "libsecret", or "auto"


logger = logging.getLogger("halinuxcompanion")


class Companion:
    """Class encolsing a companion instance
    https://developers.home-assistant.io/docs/api/native-app-integration/setup
    """

    # TODO: This class is just a huge pile of things
    # TODO: Revisit this device_id which must be unique, used for notification events
    device_id: str = platform.node()
    # TODO: Get the default values from something that helps sets releases.
    app_name: str = "Linux Companion"
    app_version: str = "0.0.1"
    app_id: str = app_name.replace(" ", "_") + app_version
    device_name: str = platform.node()
    manufacturer: str = platform.system()
    model: str = "Computer"
    os_name: str = platform.system()
    os_version: str = platform.release()
    # TODO: Encryption requires https://github.com/jedisct1/libsodium
    encryption_key: str = "NOT IMPLEMENTED"
    supports_encryption: bool = False
    app_data: dict = {}
    notifier: bool = False
    refresh_interval: int = 15
    computer_ip: str = ""
    computer_port: int = 8400
    ha_url: str = "http://localhost:8123"
    ha_token: Optional[str] = None
    url_program: str = ""
    commands: Dict[str, CommandConfig] = {}
    sensors: Dict[str, bool] = {}
    sensor_names: Dict[str, str] = {}

    def __init__(self, config: dict):
        # Load only allowed values
        parsed = CompanionConfig.model_validate(config)
        self.load_config_from_model(parsed)

    def load_config_from_model(self, config: CompanionConfig):
        self.ha_url = config.ha_url.rstrip("/")
        self.ha_token = config.ha_token
        self.device_id = config.device_id
        self.device_name = config.device_name if config.device_name else self.device_name
        self.manufacturer = config.manufacturer if config.manufacturer else self.manufacturer
        self.model = config.model if config.model else self.model
        self.computer_ip = config.computer_ip
        self.computer_port = config.computer_port
        self.refresh_interval = config.refresh_interval if config.refresh_interval else self.refresh_interval

        from halinuxcompanion.sensors import __all__ as all_sensors

        for name, sensor in config.sensors.items():
            if name not in all_sensors:
                logger.error("Sensor %s doesn't exist", name)
                exit(1)
            else:
                self.sensors[name] = sensor.enabled
                # Store custom sensor name if provided
                if sensor.name:
                    self.sensor_names[name] = sensor.name

        if config.services and config.services.notifications and config.services.notifications.enabled:
            self.notifier = True
            # Push token will be generated/loaded in load_or_register
            self.url_program = config.services.notifications.url_program
            self.commands = config.services.notifications.commands

    def registration_payload(self) -> dict:
        return {
            "device_id": self.device_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "device_name": self.device_name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "supports_encryption": self.supports_encryption,
            "app_data": self.app_data,
        }

    async def check_registration(self, api: "API", data: dict) -> bool:
        """
        Check if the current registration is still valid
        """
        logger.info("Checking if device is already registered")
        api.process_registration_data(data)
        res = await api.webhook_post("get_config", data={"type": "get_config"})
        if res.status == 200:
            return True
        elif res.status == SC_INTEGRATION_DELETED:
            logger.info("Device registration has been deleted, need to register again")
            return False
        else:
            logger.error("Device registration failed with status code %s", res.status)
            raise Exception("Device registration failed " + str(res.status))

    async def register(self, api: "API", max_retries: int = 3) -> dict:
        """Register the companion with Home Assistant with retry logic.
        
        :param api: API instance for communication
        :param max_retries: Maximum number of registration attempts
        :return: registration_data if successful
        :raises: Exception if registration fails after all retries
        """
        register_data = json.dumps(self.registration_payload())
        last_exception = None
        
        for attempt in range(max_retries):
            if attempt > 0:
                # Exponential backoff: 2^attempt seconds (2s, 4s, 8s...)
                wait_time = 2 ** attempt
                logger.warning(f"Registration attempt {attempt + 1}/{max_retries}, waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            
            logger.info("Registering companion device with payload:%s", register_data)
            
            try:
                res = await api.post("/api/mobile_app/registrations", data=register_data)
                
                if res.ok:
                    data = await res.json()
                    logger.info("Device Registration successful: %s", data)
                    self.save_registration_data(data)
                    return data
                else:
                    text = await res.text()
                    error_msg = f"Device Registration failed with status code {res.status}, text: {text}"
                    logger.error(error_msg)
                    last_exception = Exception(error_msg)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Registration attempt {attempt + 1} failed with error")
                last_exception = e
        
        logger.critical(f"Device Registration failed after {max_retries} attempts")
        raise last_exception

    async def load_or_register(self, api: "API") -> dict:
        """
        Load registration data from disk or register the companion APP
        
        :return: registration_data
        :raises: Exception if registration fails
        """
        registration_data = self.load_registration_data()

        # Load or generate push token if notifications are enabled
        if self.notifier:
            state_data = self._load_state_data()
            if state_data and "push_token" in state_data:
                # Use existing push token
                push_token = state_data["push_token"]
                logger.info("Loaded existing push token")
            else:
                # Generate new secure push token
                push_token = secrets.token_urlsafe(32)
                logger.info("Generated new secure push token")
                # Save it for future use
                self._save_state_data({"push_token": push_token})

            self.app_data = {
                "push_token": push_token,
                "push_url": f"http://{self.computer_ip}:{self.computer_port}/notify",
            }

        if registration_data:
            logger.info("Loaded existing registration data from disk %s", registration_data)
            
            # Validate required fields (only webhook_id is truly required)
            if not registration_data.get("webhook_id"):
                logger.warning("Registration data is incomplete (missing webhook_id), re-registering")
                return await self.register(api)
            
            if await self.check_registration(api, registration_data):
                logger.info("Device already registered")
                return registration_data
            else:
                logger.warning("Device registration check failed, re-registering")
                return await self.register(api)
                
        return await self.register(api)

    def _get_state_dir(self) -> Path:
        """Get the state directory path using XDG_STATE_HOME."""
        return get_state_dir()

    def _get_registration_path(self) -> Path:
        """Get the registration file path."""
        return self._get_state_dir() / "registration.json"

    def save_registration_data(self, data: dict):
        # store data in $XDG_STATE_HOME/halinuxcompanion/registration.json
        registration_path = self._get_registration_path()
        registration_path.parent.mkdir(parents=True, exist_ok=True)

        with open(registration_path, "w") as f:
            f.write(json.dumps(data))

    def load_registration_data(self) -> Optional[dict]:
        registration_path = self._get_registration_path()

        if registration_path.exists():
            with open(registration_path, "r") as f:
                return json.load(f)
        return None

    def _get_state_path(self) -> Path:
        """Get the state file path."""
        return self._get_state_dir() / "state.json"

    def _load_state_data(self) -> Optional[dict]:
        """Load state data including push token."""
        state_path = self._get_state_path()

        if state_path.exists():
            with open(state_path, "r") as f:
                return json.load(f)
        return None

    def _save_state_data(self, data: dict):
        """Save state data including push token."""
        state_path = self._get_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data and update it
        existing_data = self._load_state_data() or {}
        existing_data.update(data)

        with open(state_path, "w") as f:
            f.write(json.dumps(existing_data))
