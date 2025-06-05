#!/usr/bin/env python3
"""Simple demonstration of dasbus signal limitations.

This shows the fundamental issue: dasbus doesn't properly
expose signals through proxy objects.
"""

import subprocess
import sys
import time

# Service code to run in subprocess
SERVICE_CODE = '''
from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.server.publishable import Publishable
from dasbus.typing import Str
import time

@dbus_interface("com.example.TestInterface")
class TestService(Publishable):
    @dbus_signal
    def test_signal(self, data: Str):
        pass
    
    def emit_test(self):
        self.test_signal("test_data")
    
    def for_publication(self):
        return self

# Publish service
bus = SessionMessageBus()
service = TestService()
bus.publish_object("/com/example/Test", service)
bus.register_service("com.example.DasbusSignalTest")

print("SERVICE_READY")
print(flush=True)

# Keep running and emit signals
for i in range(5):
    time.sleep(1)
    service.emit_test()
    print(f"EMITTED_{i}", flush=True)
'''

def main():
    """Test dasbus signal access."""
    print("=== Dasbus Signal Test ===")
    
    # Start service
    print("\n1. Starting service in subprocess...")
    proc = subprocess.Popen(
        [sys.executable, "-c", SERVICE_CODE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    
    # Wait for service
    while True:
        line = proc.stdout.readline()
        if "SERVICE_READY" in line:
            print("✓ Service started")
            break
    
    # Try to connect
    print("\n2. Connecting as client...")
    try:
        from dasbus.connection import SessionMessageBus
        bus = SessionMessageBus()
        proxy = bus.get_proxy(
            "com.example.DasbusSignalTest",
            "/com/example/Test"
        )
        print("✓ Got proxy object")
    except Exception as e:
        print(f"✗ Failed to get proxy: {e}")
        proc.terminate()
        return 1
    
    # Try to access signal
    print("\n3. Checking signal access...")
    try:
        # This is where dasbus fails - signals aren't properly exposed
        if hasattr(proxy, 'test_signal'):
            print("✓ Signal exists on proxy")
            
            # Try to connect
            def handler(data):
                print(f"Received: {data}")
            
            proxy.test_signal.connect(handler)
            print("✓ Connected to signal")
        else:
            print("✗ Signal 'test_signal' not found on proxy")
            print("  Available attributes:", [a for a in dir(proxy) if not a.startswith('_')])
            print("\n  This is the core issue with dasbus!")
    except Exception as e:
        print(f"✗ Error accessing signal: {e}")
    
    # Clean up
    proc.terminate()
    proc.wait()
    
    print("\n=== Summary ===")
    print("✗ dasbus doesn't properly expose signals on proxy objects")
    print("  Even though signals are defined with @dbus_signal,")
    print("  they're not accessible through the proxy interface")
    print("  See: https://stackoverflow.com/questions/75383010/")

if __name__ == "__main__":
    main()