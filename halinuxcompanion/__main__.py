from halinuxcompanion.api import API, Server
from halinuxcompanion.dbus import Dbus
from halinuxcompanion.notifier import Notifier
from halinuxcompanion.companion import Companion
from halinuxcompanion.sensor import Sensor, SensorManager
from halinuxcompanion.sensors import *

import asyncio
import json
import logging
import argparse
import os
from pathlib import Path
import toml
# set logging level using and environment variable
logger = logging.getLogger("halinuxcompanion")


def load_config(file: Path) -> dict:
    logger.info("Reading configuration file %s", file)
    try:
        with open(file, "r") as f:
            if file.suffix.lower() == ".json":
                return json.load(f)
            elif file.suffix.lower() in [".toml", ".tml"]:
                return toml.load(f)
            else:
                # Try to detect format from content
                content = f.read()
                f.seek(0)
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return toml.loads(content)
    except FileNotFoundError:
        logger.critical("Config file not found %s, exiting now", file)
        exit(1)
    except (json.JSONDecodeError, toml.TomlDecodeError) as e:
        logger.critical("Config file parse error in %s: %s", file, e)
        exit(1)


def get_default_config_path() -> Path:
    """Get the default config path using XDG_CONFIG_HOME."""
    config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = config_home / "halinuxcompanion"
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
    args = parser.parse_args()
    return args


async def main():
    """ Main function
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

    companion = Companion(config)  # Companion objet where configuration is stored
    api = API(companion)  # API client to send data to Home Assistant
    server = Server(companion)  # HTTP server that handles notifications
    # Initialize dbus connections
    bus = Dbus()
    await bus.init()
    # Register sensors
    sensors = list(filter(lambda x: x.config_name in companion.sensors, Sensor.instances))
    # Apply custom sensor names from config
    for sensor in sensors:
        if sensor.config_name in companion.sensor_names:
            sensor.name = companion.sensor_names[sensor.config_name]
    sensor_manager = SensorManager(api, sensors, bus)

    # If the device can't be registered exit immidiately, nothing to do.
    ok, reg_data = await companion.load_or_register(api)
    if not ok:
        logger.critical("Device registration failed, exiting now")
        exit(1)

    api.process_registration_data(reg_data)

    # If sensors can't be registered exit immidiately, nothing to do.
    if not await sensor_manager.register_sensors():
        logger.critical("Sensor registration failed, exiting now")
        exit(1)

    # Initialize the notifier which implies the webserver and the dbus interface
    if companion.notifier:
        # TODO: Session bus is initialized already.
        # DBus session client to send desktop notifications and listen to signals
        # Notifier behavior: HA -> Webserver -> dbus ... dbus -> event_handler -> HA
        notifier = Notifier()
        await notifier.init(bus, api, server, companion)
        await server.start()

    interval = companion.refresh_interval
    # Loop forever updating sensors.
    while True:
        await sensor_manager.update_sensors()
        await asyncio.sleep(interval)


def run():
    """Entry point for the console script."""
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())


if __name__ == "__main__":
    run()
