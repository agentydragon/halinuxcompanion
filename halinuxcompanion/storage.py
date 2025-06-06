"""Secure storage for Home Assistant Linux Companion."""

import logging

import keyring

from halinuxcompanion.api.models import Registration

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "halinuxcompanion"
KEYRING_KEY = "registration"


def save_registration(registration: Registration) -> None:
    """Save registration data securely.

    Args:
        registration: The registration data to save.
    """
    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, registration.model_dump_json())
    logger.info("Saved registration data to keyring")


def load_registration() -> Registration | None:
    """Load registration data from secure storage.

    Returns:
        The registration data if found, None otherwise.
    """
    if data := keyring.get_password(KEYRING_SERVICE, KEYRING_KEY):
        return Registration.model_validate_json(data)
    return None


def delete_registration() -> None:
    """Delete registration data from secure storage."""
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_KEY)
        logger.info("Deleted registration data from keyring")
    except keyring.errors.PasswordDeleteError:
        logger.debug("No registration data to delete")
