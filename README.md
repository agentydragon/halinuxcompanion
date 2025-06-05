# HALinuxCompanion

Linux desktop companion for Home Assistant - provides sensor data and notifications.

## Development Setup

This project requires a clean Python environment. We recommend using pyenv and virtualenv to avoid conflicts with system-wide packages (particularly pytest-socket which can interfere with DBus tests).

```bash
# Using pyenv (recommended)
pyenv local 3.11.12  # or another Python 3.10+ version
python -m venv venv
source venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Run tests
pytest
```
