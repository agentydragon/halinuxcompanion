"""Shared data models for halinuxcompanion."""

from typing import Optional

from pydantic import BaseModel


class RegistrationData(BaseModel):
    """Data returned from Home Assistant device registration."""

    secret: Optional[str] = None
    webhook_id: str
    cloudhook_url: Optional[str] = ""
    remote_ui_url: Optional[str] = ""

    @property
    def webhook_path(self) -> str:
        """Get the webhook API path."""
        return f"/api/webhook/{self.webhook_id}"
