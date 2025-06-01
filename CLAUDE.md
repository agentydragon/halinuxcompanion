# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Home Assistant Linux Companion is a Python application that provides sensor data from a Linux desktop to Home Assistant and receives notifications. It acts as a bridge between Linux systems and Home Assistant's mobile_app integration.

## Development Commands

### Setup
```bash
# Development installation
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"
```

### Authentication
```bash
# Run OAuth authentication flow (recommended)
halinuxcompanion oauth

# Or configure long-lived token in config file
# ha_token: "your-long-lived-token"

# Configure storage backend in config file
# storage_backend: "auto"  # auto, libsecret, or file
```

### Running
```bash
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

## Architecture

### Core Components

1. **Configuration System** (`companion.py: CompanionConfig`)
   - Supports TOML (preferred) and JSON formats
   - Uses Pydantic for validation
   - Stores registration in `~/.local/state/halinuxcompanion/registration.json`
   - Secret storage backends: libsecret (system keyring) or file storage with permission checks

2. **Sensor System** (`sensor.py`, `sensors/`)
   - Base `Sensor` class with auto-registration pattern
   - `SensorManager` handles periodic updates
   - Sensors can subscribe to D-Bus signals for event-driven updates
   - All sensor updates use webhook API after initial registration

3. **API Communication** (`api.py`)
   - Initial registration uses Home Assistant REST API with long-lived token
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
- Sensors self-register using `__init_subclass__`
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
  - Fixed callback port 9736 for client_id consistency
- Most operations after registration use webhook authentication
- Configuration examples: `config.example.toml` (preferred) and `config.example.json`

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

## Coding Reminders
- Make sure to register hardware classes in halinuxcompanion/sensor.py and other places so they work
