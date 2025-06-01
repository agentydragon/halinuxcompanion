import argparse
import asyncio
import logging
import sys
import textwrap
from pathlib import Path

import toml
from tabulate import tabulate
from xdg_base_dirs import xdg_config_home

from .api import API, Server
from .companion import Companion, CompanionConfig, get_state_dir
from .dbus import Dbus
from .hardware_base import DeviceClass
from .notifier import Notifier
from .oauth import OAuthFlow
from .secret_storage import FileSecretStorage, LibSecretStorage, SecretStorage, SecretStorageBackend
from .secret_storage.file import check_file_permissions
from .sensor import HARDWARE_CLASSES, SensorManager

# set logging level using and environment variable
logger = logging.getLogger("halinuxcompanion")


def load_config(file: Path) -> CompanionConfig:
    logger.info(f"Reading configuration from {file}")

    # First check if file exists
    if not file.exists():
        sys.exit(f"Config file {file} not found, exiting")

    with file.open() as f:
        try:
            data = toml.load(f)
            config = CompanionConfig.model_validate(data)
        except toml.TomlDecodeError:
            sys.exit(f"Config file parse error in {file}")

    # Check file permissions if it contains a token
    if config.ha_token:
        check_file_permissions(file)

    return config  # type: ignore[no-any-return]


def get_default_config_path() -> Path:
    """Get the default config path using XDG_CONFIG_HOME."""
    return xdg_config_home() / "halinuxcompanion" / "config.toml"  # type: ignore[no-any-return]


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


async def print_sensor_states(companion: Companion) -> None:
    """Print current states of all enabled sensors."""
    print("\n=== Sensor States ===\n")

    hardware = []
    for hw_class in HARDWARE_CLASSES.values():
        hw_config = getattr(companion.hardware, hw_class.config_field)
        if not hw_config.enabled:
            continue
        hardware.append(hw_class(hw_config))

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


async def cleanup_sensors(companion: Companion) -> None:
    """List and optionally delete sensors that are no longer being updated."""

    # Discover all sensors that would be created
    current_sensor_ids: set[str] = set()
    for hw_name, hw_class in HARDWARE_CLASSES.items():
        hw_config = getattr(companion.hardware, hw_name, None)
        if not hw_config or not hw_config.enabled:
            continue
        discovered = await hw_class(hw_config).discover_sensors()
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
    parser = argparse.ArgumentParser(description="Home Assistant Linux Companion")

    # Global arguments
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

    # Create subparsers
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # OAuth command
    _oauth_parser = subparsers.add_parser("oauth", help="Run OAuth authentication flow")

    # Sensor states command
    _sensor_states_parser = subparsers.add_parser("sensor-states", help="Print current sensor states")

    # Cleanup sensors command
    _cleanup_parser = subparsers.add_parser(
        "cleanup-sensors",
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
    config = load_config(args.config)

    # Set logging level: command line > config > default INFO
    log_level = args.loglevel or config.loglevel or "INFO"
    logging.basicConfig(level=log_level)

    # Get the storage backend
    state_dir = get_state_dir()
    storage: SecretStorage
    if config.storage_backend == SecretStorageBackend.FILE:
        storage = FileSecretStorage(state_dir)
    elif config.storage_backend == SecretStorageBackend.LIBSECRET:
        storage = LibSecretStorage()
    else:
        raise ValueError(f"Invalid {config.storage_backend = }")

    # Companion objet where configuration is stored
    companion = Companion(config)

    # Use unified server for all operations
    async with Server(companion) as server:
        # Handle OAuth separately (doesn't need API)
        if args.command == "oauth":
            await OAuthFlow(companion.ha_url, redirect_port=companion.http_port).run(storage, server)
            print("\nOAuth authentication successful.")
            return

        # All other commands need API setup
        api = API(companion, storage)
        await companion.load_or_register(api)
        api.registration = companion.state.registration_data

        if args.command == "sensor-states":
            await print_sensor_states(companion)
            return

        if args.command == "cleanup-sensors":
            await cleanup_sensors(companion)
            return

        # Default behavior: run the service
        # Check if we have any authentication configured
        if not api.has_valid_auth():
            logger.critical(
                "No valid authentication found!\n\n"
                "Please configure authentication using one of these methods:\n"
                "1. Add 'ha_token' to your config file with a long-lived access token\n"
                "   See: https://www.home-assistant.io/docs/authentication/#your-account-profile\n"
                "2. Run OAuth authentication: halinuxcompanion oauth\n"
            )
            sys.exit(1)

        # Initialize dbus connections
        bus = await Dbus.create()

        # Register sensors
        sensor_manager = SensorManager(api=api, dbus=bus, hardware_config=companion.hardware)

        try:
            await sensor_manager.discover_and_register_sensors()
        except Exception:
            logger.critical("Sensor registration failed", exc_info=True)
            raise

        # Initialize the notifier which implies the webserver and the dbus interface
        if companion.notifier:
            await Notifier().init(bus, api, server, companion)

        # Loop forever updating sensors.
        while True:
            await sensor_manager.update_sensors()
            await asyncio.sleep(companion.refresh_interval)


def run():
    """Entry point for the console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
