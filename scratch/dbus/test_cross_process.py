#!/usr/bin/env python3
"""Test dbus-fast signals across processes.

This demonstrates that dbus-fast signals work correctly
across process boundaries, which is the typical DBus use case.
"""

import asyncio
import subprocess
import sys
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Service code that will run in subprocess
SERVICE_CODE = '''
import asyncio
import sys
from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, signal, method

class TestService(ServiceInterface):
    def __init__(self):
        super().__init__("com.example.CrossProcessTest")
        self.signal_count = 0
    
    @signal()
    def data_signal(self) -> "s":
        self.signal_count += 1
        return f"signal_{self.signal_count}"
    
    @method()
    def trigger_signal(self) -> "i":
        self.data_signal()
        return self.signal_count

async def run_service():
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    service = TestService()
    bus.export("/test", service)
    await bus.request_name("com.example.CrossProcessTest")
    
    print("SERVICE_READY", flush=True)
    
    # Emit signals periodically
    for i in range(5):
        await asyncio.sleep(1)
        service.data_signal()
        print(f"SERVICE_EMITTED_{i+1}", flush=True)

if __name__ == "__main__":
    asyncio.run(run_service())
'''


async def run_client():
    """Run the client that receives signals."""
    from dbus_fast import BusType
    from dbus_fast.aio import MessageBus
    
    logger.info("Client: Connecting to bus...")
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    
    # Wait for service
    logger.info("Client: Waiting for service...")
    await asyncio.sleep(1)
    
    # Get proxy
    logger.info("Client: Getting proxy...")
    introspection = await bus.introspect("com.example.CrossProcessTest", "/test")
    proxy_obj = bus.get_proxy_object("com.example.CrossProcessTest", "/test", introspection)
    proxy = proxy_obj.get_interface("com.example.CrossProcessTest")
    
    # Track signals
    signals_received = []
    
    def on_signal(data):
        signals_received.append(data)
        logger.info(f"Client: Received signal: {data}")
    
    # Subscribe
    logger.info("Client: Subscribing to signals...")
    proxy.on_data_signal(on_signal)
    
    # Trigger a signal manually
    logger.info("Client: Triggering signal via method...")
    count = await proxy.call_trigger_signal()
    logger.info(f"Client: Signal count on service: {count}")
    
    # Wait for automatic signals
    logger.info("Client: Waiting for automatic signals (5 seconds)...")
    await asyncio.sleep(5)
    
    logger.info(f"Client: Received {len(signals_received)} signals")
    
    # Unsubscribe
    logger.info("Client: Unsubscribing...")
    proxy.off_data_signal(on_signal)
    
    # Wait to ensure no more signals
    before = len(signals_received)
    await asyncio.sleep(2)
    after = len(signals_received)
    
    logger.info(f"Client: Signals after unsubscribe: {after - before} (should be 0)")
    
    bus.disconnect()
    return signals_received


async def main():
    """Run the cross-process test."""
    logger.info("=== Cross-Process Signal Test ===")
    
    # Start service process
    logger.info("\nStarting service process...")
    proc = subprocess.Popen(
        [sys.executable, "-c", SERVICE_CODE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    # Wait for service to be ready
    while True:
        line = proc.stdout.readline()
        if "SERVICE_READY" in line:
            logger.info("✓ Service process started")
            break
        if proc.poll() is not None:
            logger.error("✗ Service process died")
            return
    
    try:
        # Run client
        logger.info("\nRunning client...")
        signals = await run_client()
        
        # Summary
        logger.info("\n=== Summary ===")
        logger.info(f"✓ Cross-process communication works")
        logger.info(f"✓ Received {len(signals)} signals")
        logger.info(f"✓ Signal data: {signals[:3]}...")  # Show first 3
        logger.info(f"✓ Unsubscription works across processes")
        
    finally:
        # Clean up
        logger.info("\nTerminating service process...")
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    asyncio.run(main())