import argparse
import asyncio
import logging
import sys
import textwrap
from pathlib import Path
from typing import Dict, List

import toml
from xdg_base_dirs import xdg_config_home, xdg_state_home

from .api import API, Server
from .companion import Companion, CompanionConfig
from .dbus import Dbus
from .hardware_base import HardwareSensor
from .notifier import Notifier
from .oauth import OAuthFlow
from .secret_storage.file import FileSecretStorage, check_file_permissions
from .secrets import LibSecretStorage, SecretStorageBackend
from .sensor import HARDWARE_CLASSES, SensorManager

# set logging level using and environment variable
logger = logging.getLogger("halinuxcompanion")


def load_config(file: Path) -> CompanionConfig:
    logger.info(f"Reading configuration from {file}")

    # First check if file exists
    if not file.exists():
        sys.exit(f"Config file {file} not found, exiting")

    with open(file) as f:
        try:
            config = CompanionConfig.model_validate(toml.load(f))
        except toml.TomlDecodeError:
            sys.exit(f"Config file parse error in {file}")

    # Check file permissions if it contains a token
    if config.ha_token:
        check_file_permissions(file)

    return config


def get_default_config_path() -> Path:
    """Get the default config path using XDG_CONFIG_HOME."""
    return xdg_config_home() / "halinuxcompanion" / "config.toml"


def sensor_line(sensor):
    # Format sensor type indicator
    sensor_icons = {
        "temperature": "🌡️",
        "battery": "🔋",
        "connectivity": "🔗",
        "power": "⚡",
        "duration": "⏱️",
        "data_size": "💾",
        "opening": "🚪",
        "motion": "📹",
        "frequency": "📡",
        "voltage": "⚡",
        "energy_storage": "🔋",
    }
    # Print sensor info with proper indentation based on whether we have multiple pieces
    text = [
        f"{sensor_icons.get(sensor.device_class, '📊')} {sensor.name} {sensor.state_str()}"
    ]
    # Print attributes if present
    if sensor.attributes:
        text.append(
            " ".join(f"{key}={value}" for key, value in sensor.attributes.items())
        )
    return text


async def print_sensor_states(companion: Companion) -> None:
    """Print current states of all enabled sensors."""
    print("\n=== Sensor States ===\n")

    # sensor => hardware class
    sensor_info = {}
    update_futures = []

    # Discover sensors for each enabled hardware class
    for hw_name, hw_class in HARDWARE_CLASSES.items():
        hw_config = getattr(companion.hardware, hw_name, None)
        if not hw_config or not hw_config.enabled:
            continue
        hw_instance = hw_class(hw_config)  # type: ignore[abstract]
        discovered = await hw_instance.discover_sensors()
        for sensor in discovered:
            sensor_info[sensor] = hw_name
        update_futures.append(hw_instance.update_all_sensors())

    # Update all sensors in parallel
    await asyncio.gather(*update_futures)

    # Group sensors by hardware class and piece for printing
    hw_sensors: Dict[str, Dict[str, List[HardwareSensor]]] = {}
    for sensor, hw_name in sensor_info.items():
        if hw_name not in hw_sensors:
            hw_sensors[hw_name] = {}

        # Group by hardware piece ID
        hw_sensors[hw_name].setdefault(sensor.hardware_id, []).append(sensor)

    # Print results
    for hw_name, pieces in sorted(hw_sensors.items()):
        print(f"\n  {hw_name.upper()}")
        print(f"  {'=' * len(hw_name)}")

        if not pieces:
            print("    No sensors discovered")
            continue

        # Sort pieces by ID for consistent output
        for piece_id, sensors in sorted(pieces.items()):
            # Print piece header if there are multiple pieces
            if len(pieces) > 1:
                print(f"\n    [{piece_id}]")

            for sensor in sensors:
                text = sensor_line(sensor)
                print(
                    textwrap.indent(
                        "\n".join(text), "    " if len(pieces) > 1 else "  "
                    )
                )


async def cleanup_sensors(companion: Companion) -> None:
    """List and optionally delete sensors that are no longer being updated."""

    # Discover all sensors that would be created
    current_sensor_ids: set[str] = set()
    for hw_name, hw_class in HARDWARE_CLASSES.items():
        hw_config = getattr(companion.hardware, hw_name, None)
        if not hw_config or not hw_config.enabled:
            continue
        discovered = await hw_class(hw_config).discover_sensors()  # type: ignore[abstract]
        current_sensor_ids.update(sensor.unique_id for sensor in discovered)

    print("\n=== Sensor Cleanup Tool ===\n")
    print(f"Currently active sensors: {len(current_sensor_ids)}")

    print("\nActive sensor IDs that WILL be kept:")
    for sensor_id in sorted(current_sensor_ids):
        print(f"  ✓ {sensor_id}")

    print("\n" + "=" * 50)
    print("CLEANUP OPTIONS:")
    print("=" * 50)

    print("\n(a) Currently unused sensors:")
    print("    - Sensors that exist in HA but are NOT in the active list above")
    print("    - These will never receive updates from this companion instance")

    print("\n(b) Stale sensors (not updated for >30 days):")
    print("    - Sensors that haven't been updated in over 30 days")
    print("    - May indicate old/renamed sensors from previous configurations")

    print("\n" + "=" * 50)
    print("TO VIEW AND DELETE SENSORS:")
    print("=" * 50)

    # Get Home Assistant URL for direct link; TODO: unclear if OK with moves etc
    print(f"\n1. Open: {companion.ha_url}/config/devices")
    print(f"2. Search for device: '{companion.device_name}'")
    print("3. Click on the device to see all entities")
    print("4. Look for entities NOT in the active list above")
    print("5. Check 'Last updated' timestamp for each entity")
    print("6. Delete unwanted entities using the delete button")

    print("\nNOTE: Future versions will automate this process with:")
    print("  - Automatic detection of orphaned sensors")
    print("  - Last update timestamps for each sensor")
    print("  - Bulk deletion with confirmation prompt")


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
    parser.add_argument(
        "--sensor-states",
        action="store_true",
        help="Print current sensor states and exit",
    )
    parser.add_argument(
        "--cleanup-sensors",
        action="store_true",
        help="List and optionally delete sensors that are no longer being updated",
    )
    return parser.parse_args()


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
    if level := (args.loglevel or config.loglevel):
        logger.setLevel(level)

    # Get the storage backend
    state_dir = xdg_state_home() / "halinuxcompanion"  # TODO: dedupe dirs
    if config.storage_backend == SecretStorageBackend.FILE:
        storage = FileSecretStorage(state_dir)
    elif config.storage_backend == SecretStorageBackend.LIBSECRET:
        storage = LibSecretStorage()
    else:
        raise ValueError(f"Invalid {config.storage_backend = }")

    # Companion objet where configuration is stored
    companion = Companion(config)

    # Handle OAuth flow if requested
    if args.oauth:
        await OAuthFlow(companion.ha_url).run(storage)
        print("\nOAuth authentication successful.")
        sys.exit(0)

    api = API(companion, storage)  # API client to send data to Home Assistant
    await companion.load_or_register(api)
    api.registration = companion.state.registration_data

    # Handle sensor states reporting if requested
    if args.sensor_states:
        await print_sensor_states(companion)
        sys.exit(0)

    # Handle sensor cleanup if requested
    if args.cleanup_sensors:
        await cleanup_sensors(companion)
        sys.exit(0)

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
    # Register sensors
    sensor_manager = SensorManager(api=api, dbus=bus)

    try:
        await sensor_manager.discover_and_register_sensors()
    except:
        logger.critical("Sensor registration failed")
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
        await sensor_manager.update_sensors()
        await asyncio.sleep(companion.refresh_interval)


def run():
    """Entry point for the console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
