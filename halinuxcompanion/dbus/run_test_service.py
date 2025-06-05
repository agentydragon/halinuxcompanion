#!/usr/bin/env python3
"""Run test DBus service in a separate process.

This is used by the integration tests to run a DBus service in a subprocess,
avoiding the dbus-fast limitation of not working in the same process.
"""

import asyncio
import logging
import signal
import sys

from halinuxcompanion.dbus.test_service import SampleDBusService

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    service_name = sys.argv[1] if len(sys.argv) > 1 else "com.example.TestService"
    service = SampleDBusService(service_name)

    logger.info(f"Starting service {service_name}...")
    await service.start()
    print(f"Service {service_name} started!", flush=True)  # Integration test looks for this

    # Give the bus a moment to fully register everything
    await asyncio.sleep(0.5)

    # Set up signal handler for clean shutdown
    stop_event = asyncio.Event()

    def handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, stopping...")
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Emit test signals periodically
    async def emit_signals():
        counter = 0
        try:
            while not stop_event.is_set():
                await asyncio.sleep(2)
                if not stop_event.is_set() and service.is_running():
                    counter += 1
                    logger.info(f"Emitting signal #{counter}")
                    await service.emit_test_signal()
        except asyncio.CancelledError:
            pass

    # Run signal emitter task
    emit_task = asyncio.create_task(emit_signals())

    # Timeout task - exit after 60 seconds to prevent infinite running
    async def timeout_task():
        await asyncio.sleep(60)
        logger.warning("Service timeout reached (60s), stopping...")
        stop_event.set()

    timeout = asyncio.create_task(timeout_task())

    try:
        # Wait for stop signal or timeout
        await stop_event.wait()
    finally:
        emit_task.cancel()
        timeout.cancel()
        try:
            await emit_task
        except asyncio.CancelledError:
            pass
        try:
            await timeout
        except asyncio.CancelledError:
            pass

        await service.stop()
        logger.info("Service stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
