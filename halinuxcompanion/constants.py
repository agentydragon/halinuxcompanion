"""Constants for Home Assistant Linux Companion."""

from datetime import timedelta

# Timing constants
BATCH_WINDOW = timedelta(seconds=0.1)
MIN_BATCH_TIMEOUT = timedelta(seconds=0.01)

# API constants
WEBHOOK_TIMEOUT = timedelta(seconds=30)

# Application metadata
APP_ID = "halinuxcompanion"
APP_NAME = "HA Linux Companion"
APP_VERSION = "0.1.0"

# Default configuration
DEFAULT_WEBHOOK_PORT = 8123
DEFAULT_WEBHOOK_HOST = "127.0.0.1"
