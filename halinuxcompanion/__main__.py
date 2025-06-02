import argparse
import asyncio
import logging
import sys
import textwrap
from pathlib import Path
from typing import Any

import toml
from aiohttp import ClientSession
from tabulate import tabulate

from .api import API, Server
from .companion import Companion, CompanionConfig
from .dbus import Dbus
from .module_base import DeviceClass, Module, Sensor
from .module_config import ModulesConfig
from .notifier import Notifier
from .oauth import OAuthFlow
from .paths import get_default_config_path
from .secret_storage import FileSecretStorage, LibSecretStorage, SecretStorage, SecretStorageBackend
from .secret_storage.file import check_file_permissions
from .sensor import SensorManager


def get_enabled_module_instances(module_config: ModulesConfig) -> list[Module]:
    """Get list of enabled module instances."""
    enabled = []
    for module_class, config in module_config.get_enabled_module_classes():
        enabled.append(module_class(config))
    return enabled


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
            config: CompanionConfig = CompanionConfig.model_validate(data)
        except toml.TomlDecodeError:
            sys.exit(f"Config file parse error in {file}")

    # Check file permissions if it contains a token
    if config.ha_token:
        check_file_permissions(file)

    return config


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

    modules = get_enabled_module_instances(companion.config.hardware)

    # Discover sensors for each enabled module
    async def _discover(module_instance: Module) -> tuple[str, list[Sensor]]:
        sensors = await module_instance.discover_sensors()
        await module_instance.update_all_sensors()
        return module_instance.__class__.__name__, sensors

    module_sensors = await asyncio.gather(*[_discover(m) for m in modules])

    # Print results
    for module_name, sensors in sorted(module_sensors):
        if not sensors:
            print(f"{module_name}: No sensors discovered")
            continue

        print(f"{module_name}: {len(sensors)} sensors")
        items = []
        for sensor in sorted(sensors, key=lambda s: s.unique_id):
            items.append(
                {
                    "sensor": f"{SENSOR_ICONS.get(sensor.device_class, '📊') if sensor.device_class else '📊'} {sensor.name}",
                    "state": sensor.state_str,
                    **sensor.attributes,
                }
            )

        print(textwrap.indent(tabulate(items, headers="keys"), "  "))


async def cleanup_sensors(companion: Companion) -> None:
    """List and optionally delete sensors that are no longer being updated."""

    # Discover all sensors that would be created
    current_sensor_ids: set[str] = set()
    for module_instance in get_enabled_module_instances(companion.config.hardware):
        discovered = await module_instance.discover_sensors()
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
    parser.add_argument(
        "--expose-sensor-state",
        action="store_true",
        help="Expose sensor state on the HTTP root path (/) - WARNING: This exposes sensitive sensor data",
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


def get_storage_backend(config: CompanionConfig) -> SecretStorage:
    """Get the configured storage backend."""
    if config.storage_backend == SecretStorageBackend.FILE:
        return FileSecretStorage()
    if config.storage_backend == SecretStorageBackend.LIBSECRET:
        return LibSecretStorage()
    raise ValueError(f"Invalid {config.storage_backend = }")


async def setup_and_run_service(
    companion: Companion,
    api: API,
    server: Server,
    config: CompanionConfig,
    args: argparse.Namespace,
) -> None:
    """Set up and run the main service loop."""
    # Initialize dbus connections
    bus = await Dbus.create()

    # Set up device info for status page
    server.set_device_info(
        {
            "device_name": companion.device_name,
            "device_id": companion.device_id,
            "version": companion.companion_version,
            "ha_url": companion.ha_url,
        }
    )

    # Set up sensor state provider that only reads current state
    sensor_manager: SensorManager | None = None  # Will be set after sensor discovery

    async def get_sensor_states() -> list[dict[str, Any]]:
        """Get current sensor states without triggering updates."""
        if sensor_manager is None:
            return []
        if not sensor_manager.sensors:
            return []

        # Return all sensors in a flat list, sorted by unique_id
        sensor_data = []
        for sensor in sorted(sensor_manager.sensors, key=lambda s: s.unique_id):
            sensor_data.append(
                {
                    "unique_id": sensor.unique_id,
                    "name": sensor.name,
                    "state": sensor.state,
                    "state_str": sensor.state_str,
                    "icon": sensor.icon,
                    "attributes": sensor.attributes,
                }
            )
        return sensor_data

    server.set_sensor_state_provider(get_sensor_states)

    # Print the status page URL
    print("\n" + "=" * 60)
    print("🏠 Home Assistant Linux Companion is running!")
    print("=" * 60)
    if args.expose_sensor_state:
        print(f"\n📊 View sensor status at: http://{companion.http_host}:{companion.http_port}/")
    else:
        print("\n📊 Sensor status page disabled (use --expose-sensor-state to enable)")
    print(f"🔔 Notifications endpoint: http://{companion.http_host}:{companion.http_port}/notify")
    print(f"🔐 OAuth callback: http://{companion.http_host}:{companion.http_port}/auth/callback")
    print("\n" + "=" * 60 + "\n")

    # Register sensors - assign to the nonlocal variable
    sensor_manager = SensorManager(api=api, dbus=bus, module_config=config.hardware)

    try:
        await sensor_manager.discover_and_register_sensors()

    except Exception:
        logger.critical("Sensor registration failed", exc_info=True)
        raise

    # Initialize the notifier which implies the webserver and the dbus interface
    if config.notifications.enabled:
        push_token = companion.load_or_generate_push_token()
        notifier = Notifier(
            api=api,
            server=server,
            push_token=push_token,
            url_program=config.notifications.url_program,
            commands=config.notifications.commands,
            ha_url=config.ha_url.rstrip("/"),
        )
        await notifier.setup_dbus(bus)

    # Loop forever updating sensors.
    while True:
        await sensor_manager.update_sensors()
        await asyncio.sleep(companion.refresh_interval)


async def main() -> None:
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
    storage = get_storage_backend(config)

    # Companion objet where configuration is stored
    companion = Companion(config)

    # Create shared session and server for all operations
    async with (
        ClientSession() as session,
        Server(companion.http_host, companion.http_port, expose_sensor_state=args.expose_sensor_state) as server,
    ):
        # Handle OAuth separately (doesn't need API)
        if args.command == "oauth":
            await OAuthFlow(companion.ha_url, redirect_port=companion.http_port).run(storage, server, session)
            print("\nOAuth authentication successful.")
            return

        # All other commands need API setup
        api = API(
            instance_url=companion.ha_url,
            storage=storage,
            session=session,
        )
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

        await setup_and_run_service(companion, api, server, config, args)


def run() -> None:
    """Entry point for the console script."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
