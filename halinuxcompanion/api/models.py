"""API models for Home Assistant Mobile App integration."""

import platform
import uuid
from typing import Any

from pydantic import BaseModel, Field

from halinuxcompanion.constants import APP_ID, APP_NAME, APP_VERSION


class DeviceRegistration(BaseModel):
    """Device registration request for Home Assistant."""

    model_config = {"extra": "forbid"}

    device_id: str = Field(default_factory=lambda: str(uuid.uuid5(uuid.NAMESPACE_DNS, platform.node())))
    app_id: str = APP_ID
    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    device_name: str
    manufacturer: str = "Linux"
    model: str = platform.node()
    os_name: str = "Linux"
    os_version: str = platform.release()
    supports_encryption: bool = False
    app_data: dict[str, Any] = Field(default_factory=dict)  # TODO: Define structure if needed


class Registration(BaseModel):
    """Stored registration data.

    Combines the RegistrationResponse from HA with the instance URL.
    """

    model_config = {"extra": "forbid"}

    # From registration response
    webhook_id: str
    secret: str | None = None  # For future encryption support
    cloudhook_url: str | None = None
    remote_ui_url: str | None = None

    # Added by us
    instance_url: str
