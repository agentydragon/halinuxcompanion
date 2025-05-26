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
# Run OAuth authentication flow
halinuxcompanion --oauth

# Or configure long-lived token in config file
# ha_token: "your-long-lived-token"
```

### Running
```bash
# Run the application
halinuxcompanion

# Run with custom config
halinuxcompanion --config /path/to/config.toml
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
   - OAuth tokens stored in `~/.local/state/halinuxcompanion/oauth_tokens.json` (chmod 600)

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
- The long-lived access token is only needed for initial registration and notification events
- Most operations after registration use webhook authentication
- Configuration examples: `config.example.toml` (preferred) and `config.example.json`