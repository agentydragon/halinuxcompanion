"""Main entry point for Home Assistant Linux Companion."""

import asyncio
import logging
import sys

import aiohttp
import click
from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from halinuxcompanion.api.client import create_api_client
from halinuxcompanion.config import load_config
from halinuxcompanion.constants import BATCH_WINDOW, MIN_BATCH_TIMEOUT
from halinuxcompanion.modules.base import SensorUpdate
from halinuxcompanion.modules.battery import BatteryModule
from halinuxcompanion.modules.bluetooth import BluetoothModule
from halinuxcompanion.registration import register_device
from halinuxcompanion.storage import delete_registration, load_registration

logger = logging.getLogger(__name__)


async def run_companion():
    """Run the companion app."""
    # Load config
    config = load_config()

    # Load registration
    registration = load_registration()
    if not registration:
        raise RuntimeError("Not registered. Run 'halinuxcompanion register' first.")

    logger.info(f"Starting with webhook ID: {registration.webhook_id}")

    # Initialize DBus
    system_bus = MessageBus(bus_type=BusType.SYSTEM)
    await system_bus.connect()
    logger.info("Connected to system DBus")

    # Initialize modules
    module_classes = {
        "battery": (BatteryModule, [system_bus]),
        "bluetooth": (BluetoothModule, [system_bus, config.bluetooth_device_macs]),
    }

    modules = []
    for module_name, (module_class, args) in module_classes.items():
        if config.modules.get(module_name):
            modules.append(module_class(*args))
            info_msg = f"{module_name.capitalize()} module enabled"
            if module_name == "bluetooth":
                info_msg += f" with {len(config.bluetooth_device_macs)} devices"
            logger.info(info_msg)

    # Create API client
    async with create_api_client(registration) as client:
        # Gather and register all sensors
        all_sensors = []
        for module in modules:
            all_sensors.extend(module.sensors())

        await client.register_sensors(all_sensors)
        logger.info(f"Registered {len(all_sensors)} sensors")

        # Create update queue
        update_queue: asyncio.Queue[SensorUpdate] = asyncio.Queue()

        async def sensor_update_callback(update: SensorUpdate) -> None:
            """Queue sensor updates for batching."""
            logger.debug(f"Sensor update: {update.unique_id} = {update.state} (icon: {update.icon})")
            await update_queue.put(update)

        # Start all modules concurrently
        await asyncio.gather(*[module.start(sensor_update_callback) for module in modules])
        logger.info("All modules started")

        # Batch and send updates
        async def update_sender():
            """Batch and send sensor updates."""
            while True:
                # Collect updates for batching
                updates = []
                deadline = asyncio.get_event_loop().time() + BATCH_WINDOW.total_seconds()

                while asyncio.get_event_loop().time() < deadline:
                    try:
                        timeout = deadline - asyncio.get_event_loop().time()
                        update = await asyncio.wait_for(
                            update_queue.get(), timeout=max(MIN_BATCH_TIMEOUT.total_seconds(), timeout)
                        )
                        updates.append(update)
                    except asyncio.TimeoutError:
                        break

                if updates:
                    try:
                        await client.update_sensors(updates)
                    except aiohttp.ClientError:
                        logger.exception("Failed to send sensor updates")

        # Run update sender
        logger.info("Starting update sender")
        await update_sender()


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
def cli(debug: bool):
    """Home Assistant Linux Companion."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


@cli.command()
@click.option("--instance-url", prompt=True, help="Home Assistant URL (e.g., http://homeassistant.local:8123)")
@click.option("--device-name", help="Device name (defaults to hostname)")
def register(instance_url: str, device_name: str | None):
    """Register with Home Assistant."""
    config = load_config()
    device_name = device_name or config.device_name

    try:
        registration = asyncio.run(register_device(instance_url, device_name))
        click.echo(f"✅ Successfully registered '{device_name}' with Home Assistant!")
        click.echo(f"   Webhook ID: {registration.webhook_id}")
    except (aiohttp.ClientError, RuntimeError) as e:
        click.echo(f"❌ Registration failed: {e}", err=True)
        sys.exit(1)


@cli.command()
def unregister():
    """Remove registration data."""
    delete_registration()
    click.echo("✅ Registration data removed")


@cli.command()
@click.option("--instance-url", help="Home Assistant URL (required if not registered)")
def run(instance_url: str | None):
    """Run the companion app."""

    registration = load_registration()

    # Auto-register if not registered
    if not registration:
        if not instance_url:
            click.echo("❌ Not registered. Provide --instance-url to auto-register.", err=True)
            sys.exit(1)

        click.echo("🔐 Not registered yet, starting registration...")
        config = load_config()

        try:
            registration = asyncio.run(register_device(instance_url, config.device_name))
            click.echo(f"✅ Successfully registered '{config.device_name}'!")
        except (aiohttp.ClientError, RuntimeError) as e:
            click.echo(f"❌ Registration failed: {e}", err=True)
            sys.exit(1)

    click.echo("🚀 Starting Home Assistant Linux Companion...")

    try:
        asyncio.run(run_companion())
    except KeyboardInterrupt:
        click.echo("\n👋 Shutting down...")
    except RuntimeError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception:
        logger.exception("Fatal error")
        click.echo("❌ An unexpected error occurred. Check logs for details.", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
