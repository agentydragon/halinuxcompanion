import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import aiohttp
import toml
from xdg_base_dirs import xdg_config_home, xdg_state_home

from halinuxcompanion.api import API, AuthenticationError, Server
from halinuxcompanion.companion import Companion
from halinuxcompanion.dbus import Dbus
from halinuxcompanion.notifier import Notifier
from halinuxcompanion.secret_storage.file import check_file_permissions
from halinuxcompanion.oauth import OAuthFlow
from halinuxcompanion.secrets import SecretStorageBackend, get_secret_storage
from halinuxcompanion.sensor import Sensor, SensorManager
from halinuxcompanion.sensors import *

# set logging level using and environment variable
logger = logging.getLogger("halinuxcompanion")


def load_config(file: Path) -> dict:
    logger.info(f"Reading configuration from {file}")

    # First check if file exists
    if not file.exists():
        logger.critical(f"Config file {file} not found, exiting")
        exit(1)

    with open(file) as f:
        try:
            match file.suffix.lower():
                case ".json":
                    config = json.load(f)
                case ".toml" | ".tml":
                    config = toml.load(f)
                case _:
                    try:
                        config = json.load(f)
                    except json.JSONDecodeError:
                        f.seek(0)
                        config = toml.load(f)
        except (json.JSONDecodeError, toml.TomlDecodeError):
            logger.critical(f"Config file parse error in {file}")
            raise

    # Check file permissions if it contains a token
    if config.get("ha_token"):
        try:
            check_file_permissions(file)
        except PermissionError:
            logger.error("Security error")
            raise

    return config


def get_default_config_path() -> Path:
    """Get the default config path using XDG_CONFIG_HOME."""
    config_dir = xdg_config_home() / "halinuxcompanion"
    # Try .toml first, fall back to .json if it exists
    toml_path = config_dir / "config.toml"
    json_path = config_dir / "config.json"
    if json_path.exists() and not toml_path.exists():
        return json_path
    return toml_path


def commandline() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Home Assistan Linux Companion")
    parser.add_argument(
        "-c",
        "--config",
        help="Path to config file",
        default=get_default_config_path(),
        type=Path,
    )
    parser.add_argument(
        "-l",
        "--loglevel",
        help="Log level",
        default="",
    )
    parser.add_argument(
        "--oauth",
        action="store_true",
        help="Run OAuth authentication flow and exit",
    )
    args = parser.parse_args()
    return args


async def main():
    """Main function
    The program is fairly simple, data is sent and received to/from Home Assistant over HTTP
    Sensors:
        - Data is collected from sensors and sent to Home Assistant.
    Notifications:
        - Sent from Home Assistant to the application via embeded webserver, this are sent to the desktop using Dbus.
        - Actions are triggered in dbus listened by the application. Some are handled locally others are handled by Home
          Assistant, events are relayed to it as expected (closed and action).
    """
    args = commandline()
    logging.basicConfig(level="INFO")

    config = load_config(args.config)

    # Command line loglevel takes precedence
    if args.loglevel != "":
        logger.setLevel(args.loglevel)
    elif "loglevel" in config:
        logger.setLevel(config["loglevel"])

    # Get the storage backend
    storage_backend = SecretStorageBackend(config.get("storage_backend", "auto"))
    print(f"Using storage backend: {storage_backend.value}")
    state_dir = xdg_state_home() / "halinuxcompanion"
    storage = get_secret_storage(storage_backend, state_dir)

    # Handle OAuth flow if requested
    if args.oauth:
        ha_url = config.get("ha_url", "http://homeassistant.local:8123").rstrip("/")

        print(f"Starting OAuth authentication flow with {ha_url}")
        await OAuthFlow(ha_url).run(storage)
        print("\nOAuth authentication successful.")
        sys.exit(0)

    companion = Companion(config)  # Companion objet where configuration is stored
    api = API(companion, storage)  # API client to send data to Home Assistant

    # Check if we have any authentication configured
    if not api.has_valid_auth():
        logger.critical(
            "No valid authentication found!\n\n"
            "Please configure authentication using one of these methods:\n"
            "1. Add 'ha_token' to your config file with a long-lived access token\n"
            "   See: https://www.home-assistant.io/docs/authentication/#your-account-profile\n"
            "2. Run OAuth authentication: halinuxcompanion --oauth\n"
        )
        sys.exit(1)
    # Initialize dbus connections
    bus = Dbus()
    await bus.init()
    sensors = [sensor for sensor in Sensor.instances if sensor.config_name in companion.sensors]
    # Apply custom sensor names
    for sensor in sensors:
        if sensor.config_name in companion.sensor_names:
            sensor.name = companion.sensor_names[sensor.config_name]
    # Register sensors
    sensor_manager = SensorManager(api, sensors, bus)

    try:
        try:
            api.process_registration_data(await companion.load_or_register(api))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError):
            # If the device can't be registered exit immediately, nothing to do.
            logger.critical(f"Device registration failed")
            raise

        try:
            await sensor_manager.register_sensors()
        except:
            logger.critical("Sensor registration failed, exiting now")
            raise
    except AuthenticationError:
        logger.critical("Authentication failed")
        raise

    # Initialize the notifier which implies the webserver and the dbus interface
    if companion.notifier:
        # TODO: Session bus is initialized already.
        # DBus session client to send desktop notifications and listen to signals
        # Notifier behavior: HA -> Webserver -> dbus ... dbus -> event_handler -> HA
        server = Server(companion)  # HTTP server that handles notifications
        await Notifier().init(bus, api, server, companion)
        await server.start()

    # Loop forever updating sensors.
    while True:
        try:
            await sensor_manager.update_sensors()
        except AuthenticationError:
            logger.critical(f"Authentication failed during sensor update")
            raise
        await asyncio.sleep(companion.refresh_interval)


def run():
    """Entry point for the console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
