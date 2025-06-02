# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Home Assistant Linux Companion is a Python application that provides sensor data from a Linux desktop to Home Assistant and receives notifications. It acts as a bridge between Linux systems and Home Assistant's mobile_app integration.

## Development Commands

### Setup
```bash
pip install -e .

# With dev dependencies
pip install -e ".[dev]"
```

### Running
```bash
# Run OAuth authentication flow (recommended; alternative is long-lived access token)
halinuxcompanion oauth

# Run the application
halinuxcompanion

# Run with custom config
halinuxcompanion --config /path/to/config.toml

# View current sensor states
halinuxcompanion sensor-states

# Clean up unused sensors
halinuxcompanion cleanup-sensors
```

### Testing & Linting
```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=halinuxcompanion

# Run tests for multiple Python versions
tox

# Format code
black . --line-length 120
```

### Testing Conventions

The project follows these testing conventions:

1. **Unit Tests**: Co-located with the modules they test
   - Naming pattern: `test_*.py` in the same directory as the module
   - Example: `halinuxcompanion/secret_storage/test_file.py` tests `file.py`
   - These tests focus on testing individual units with mocked dependencies

2. **Integration Tests**: Located in the top-level `tests/` directory
   - Tests that require real external resources (network, hardware, etc.)
   - Tests that span multiple modules or test end-to-end flows
   - Example: `tests/test_oauth_server_integration.py` tests the full OAuth flow

This approach allows for quick unit test discovery while keeping integration tests organized separately.

## Architecture

### Core Components

1. **Configuration System** (`companion.py: CompanionConfig`)
   - Supports TOML format only
   - Uses Pydantic for validation
   - Stores registration in `~/.local/state/halinuxcompanion/registration.json`
   - Secret storage backends: libsecret (system keyring) or file storage with permission checks

2. **Sensor System** (`sensor.py`, `sensors/`)
   - Base `Sensor` class
   - Sensors can subscribe to D-Bus signals for event-driven updates
   - All sensor updates use webhook API after initial registration

3. **API Communication** (`api.py`)
   - Initial registration uses Home Assistant REST API with OAuth or long-lived access token
   - Subsequent updates use webhook authentication
   - Handles sensor registration, updates, and event notifications

4. **Notification System** (`notifier.py`)
   - HTTP server listens for incoming notifications from Home Assistant
   - Transforms to D-Bus desktop notifications
   - Handles notification actions and sends events back to Home Assistant

5. **D-Bus Integration** (`dbus.py`)
   - Monitors system events (sleep/wake, screensaver)
   - Sends desktop notifications
   - Handles notification action callbacks

### Key Patterns

- Fully asynchronous using asyncio
- Webhook pattern for efficient updates after registration
- D-Bus for system integration

## Important Notes

- Python 3.10+ required
- Authentication options:
  - OAuth (recommended): Automatic token refresh, browser-based authentication
  - Long-lived access token: Manual token management
- Secret storage:
  - libsecret: Uses system keyring (GNOME Keyring, KDE Wallet, etc.)
  - file: Stores with strict permission checks (600)
- OAuth requirements:
  - Must use domain name (not IP) unless connecting to local/private networks
- Most operations after registration use webhook authentication
- Configuration example: `config.example.toml`

## Code Style Guidelines

### Exception Handling
- Keep try-except blocks as minimal as possible - only wrap the specific operations that can throw the exception
- Never use broad exception catching without good reason
- Example:
  ```python
  # BAD - too broad
  try:
      with open(path, "r") as f:
          content = f.read()
      if "error" in content:
          return None
  except Exception:
      return None

  # GOOD - minimal scope
  try:
      with open(path, "r") as f:
          content = f.read()
  except (OSError, IOError) as e:
      logger.error(f"Failed to read {path}: {e}")
      return None

  if "error" in content:
      return None
  ```

### Logging Exceptions
- Use `logging.exception()` instead of `logging.error()` or others when logging exceptions inside an exception block
  - TRY400 Rule: When catching and logging exceptions, use `logger.exception()` to automatically include the full traceback

## OAuth Implementation Details

### OAuth Flow (`oauth.py`)
- Uses OAuth 2.0 authorization code flow
- Fixed port 9736 for callback server
- Automatic token refresh with 60-second expiration buffer
- IP address validation for OAuth compatibility

### Secret Storage (`secrets.py`)
- Abstract `SecretStorage` interface
- `LibSecretStorage`: System keyring integration
- `FileSecretStorage`: File-based with permission checks
- Comprehensive security validations (permissions, ownership, symlinks)

### API Authentication (`api.py`)
- Transparent handling of OAuth and long-lived tokens
- Automatic token refresh for OAuth
- Raises `AuthenticationError` when re-authentication needed

## Pending Implementation Tasks
- `@references/companion.home-assistant/docs/notifications/` should be implemented under notifier  - at least the subset that we can support

## Code Safety Guidelines

- Do not assemble URLs with plain string concat, e.g. `[f"{k}={v}" for k, v in params.items()]`. use some existing library that auto-wraps escaping etc.; apply *generally* for *all* formats that need escaping/similar.
