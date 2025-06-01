import argparse
import asyncio
import logging
import sys
import textwrap
from pathlib import Path

import toml
from tabulate import tabulate
from xdg_base_dirs import xdg_config_home, xdg_state_home

from .api import API, Server
from .companion import Companion, CompanionConfig
from .dbus import Dbus
from .hardware_base import DeviceClass
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


SENSOR_ICONS = {
    DeviceClass.TEMPERATURE: "🌡️",
    DeviceClass.BATTERY: "🔋",
    DeviceClass.POWER: "⚡",
    DeviceClass.DURATION: "⏱️",
    DeviceClass.DATA_SIZE: "💾",
    DeviceClass.OPENING: "🚪",
    # DeviceClass.FREQUENCY: "📡",
    DeviceClass.VOLTAGE: "⚡",
    DeviceClass.ENERGY_STORAGE: "🔋",
}


def sensor_line(sensor):
    # Format sensor type indicator
    # Print sensor info with proper indentation based on whether we have multiple pieces
    text = f"{SENSOR_ICONS.get(sensor.device_class, '📊')} {sensor.name} {sensor.state_str}\n"
    # Print attributes if present
    if sensor.attributes:
        text += (
            " ".join(f"{key}={value}" for key, value in sensor.attributes.items())
        ) + "\n"
    return text


async def print_sensor_states(companion: Companion) -> None:
    """Print current states of all enabled sensors."""
    print("\n=== Sensor States ===\n")

    hardware = []
    for hw_class in HARDWARE_CLASSES.values():
        hw_config = getattr(companion.hardware, hw_class.config_field)
        if not hw_config.enabled:
            continue
        hardware.append(hw_class(hw_config))  # type: ignore[abstract]

    # Discover sensors for each enabled hardware class
    async def _discover(hw_instance):
        sensors = await hw_instance.discover_sensors()
        await hw_instance.update_all_sensors()
        return hw_instance.config_field, sensors

    hw_sensors = await asyncio.gather(*[_discover(hw) for hw in hardware])

    # Print results
    for hw_name, sensors in sorted(hw_sensors):
        if not sensors:
            print(f"{hw_name}: No sensors discovered")
            continue

        print(f"{hw_name}: {len(sensors)} sensors")
        items = []
        for sensor in sorted(sensors, key=lambda s: s.unique_id):
            items.append(
                {
                    "sensor": f"{SENSOR_ICONS.get(sensor.device_class, '📊')} {sensor.name}",
                    "state": sensor.state_str,
                    **sensor.attributes,
                }
            )

        print(textwrap.indent(tabulate(items, headers="keys"), "  "))
        # for sensor in sorted(sensors, key=lambda s: s.unique_id):
        #    print(textwrap.indent(sensor_line(sensor), "  "), end="")


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
