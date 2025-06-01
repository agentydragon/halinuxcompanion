"""Shared data models for halinuxcompanion."""

from pydantic import BaseModel


class RegistrationData(BaseModel):
    """Data returned from Home Assistant device registration."""

    secret: str | None = None
    webhook_id: str
    cloudhook_url: str | None = ""
    remote_ui_url: str | None = ""

    @property
    def webhook_path(self) -> str:
        """Get the webhook API path."""
        return f"/api/webhook/{self.webhook_id}"
