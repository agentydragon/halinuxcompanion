#!/usr/bin/env python3
"""Simple test service for DBus demonstrations."""

import asyncio
from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, signal, method


class SimpleTestInterface(ServiceInterface):
    """A simple test interface with basic signal support."""
    
    def __init__(self):
        super().__init__("com.example.SimpleTest")
        self._counter = 0
    
    @signal()
    def test_signal(self) -> "s":
        """Emit a test signal with string data."""
        self._counter += 1
        return f"signal_{self._counter}"
    
    @method()
    def ping(self) -> "s":
        """Simple ping method."""
        return "pong"
    
    @method()
    def emit(self) -> "i":
        """Emit a signal and return the counter."""
        self.test_signal()
        return self._counter


async def run_service(name: str = "com.example.SimpleTestService"):
    """Run the test service."""
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    service = SimpleTestInterface()
    bus.export("/test", service)
    await bus.request_name(name)
    
    print(f"Service {name} started", flush=True)
    
    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "com.example.SimpleTestService"
    asyncio.run(run_service(name))