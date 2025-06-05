# DBus Library Testing Results

This directory contains clean demonstrations of DBus library capabilities in Python,
specifically focusing on signal support which is critical for monitoring DBus services.

## Key Finding: Use dbus-fast, not dasbus

### Critical Gotcha: Message Handler Return Values

When using `add_message_handler()` in dbus-fast, your handler MUST return `None` (or a falsy value) to allow other handlers in the chain to process the message. If you return a truthy value, it stops the processing chain.

**Wrong - This will break introspection and other internal operations:**
```python
# The lambda returns a Task object, which is truthy and blocks the chain!
bus.add_message_handler(lambda msg: asyncio.create_task(handle_msg(msg)))
```

**Correct:**
```python
def handler(msg):
    asyncio.create_task(handle_msg(msg))
    return None  # Explicitly return None to continue the chain
    
bus.add_message_handler(handler)
```

**Why this matters:** dbus-fast uses the message handler chain internally for:
- Processing introspection responses
- Handling method call replies  
- Managing signal subscriptions

If your handler returns a truthy value, you'll see symptoms like:
- Introspection timeouts (even though the service is running)
- Method calls never receiving responses
- Signals not being delivered

This was discovered the hard way when our DBusServiceMonitor couldn't connect to services!

### Test Files

1. **`test_dasbus_simple.py`** - Shows why dasbus doesn't work
   - Demonstrates that signals aren't exposed on proxy objects
   - Even with @dbus_signal decorator, signals are inaccessible
   - Known issue: https://stackoverflow.com/questions/75383010/

2. **`test_dbus_fast_success.py`** - Shows dbus-fast working correctly
   - Clean signal subscription with `proxy.on_<signal_name>(callback)`
   - Easy unsubscription with `proxy.off_<signal_name>(callback)`
   - Proper introspection support

3. **`test_cross_process.py`** - Demonstrates cross-process signals
   - Real-world scenario with service in separate process
   - Shows signal delivery and unsubscription work correctly
   - This is how DBus is typically used

4. **`simple_test_service.py`** - Reusable test service
   - Basic service implementation for testing
   - Can be run standalone or imported

## Running the Tests

```bash
# Show why dasbus fails
python test_dasbus_simple.py

# Show dbus-fast working
python test_dbus_fast_success.py

# Test cross-process signals
python test_cross_process.py

# Run standalone test service
python simple_test_service.py [optional-service-name]
```

## dbus-fast Signal Pattern

```python
# Service side - define signal
@signal()
def my_signal(self) -> "s":  # Return type defines DBus signature
    return "signal_data"

# Client side - subscribe
def handler(data):
    print(f"Received: {data}")

proxy.on_my_signal(handler)

# Client side - unsubscribe
proxy.off_my_signal(handler)
```

## Why This Matters

For the halinuxcompanion project, we need to:
1. Monitor when services appear/disappear
2. Subscribe to service-specific signals
3. Clean up subscriptions when services go away

Only dbus-fast provides the necessary functionality for this use case.