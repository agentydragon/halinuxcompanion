from unittest.mock import AsyncMock, MagicMock

import pytest

from halinuxcompanion.companion import CommandConfig, Companion, CompanionConfig, NotificationServiceConfig
from halinuxcompanion.module_config import ModulesConfig
from halinuxcompanion.notifier import Notifier
from halinuxcompanion.secret_storage import SecretStorageBackend


def setup_companion() -> Companion:
    config = CompanionConfig(
        ha_url="http://localhost:9999/",
        ha_token="test_token",
        device_id="testpc",
        device_name="test",
        manufacturer="test",
        model="Computer",
        local_http_host="localhost",
        local_http_port=8400,
        refresh_interval=15,
        loglevel="INFO",
        storage_backend=SecretStorageBackend.FILE,
        hardware=ModulesConfig(),  # All disabled by default
        notifications=NotificationServiceConfig(
            enabled=True,
            url_program="xdg-open",
            commands={
                "command_suspend": CommandConfig(name="Suspend", command=["ls"]),
            },
        ),
    )
    companion = Companion(config)
    return companion


def setup_notifier() -> Notifier:
    from unittest.mock import MagicMock

    # Create mock dependencies
    mock_api = MagicMock()
    mock_server = MagicMock()

    notifier = Notifier(
        api=mock_api,
        server=mock_server,
        push_token="d0f7bd90-7b23-11ee-852f-0 0d861ab3a9c",
        url_program="xdg-open",
        commands={
            "command_suspend": CommandConfig(name="Suspend", command=["ls"]),
        },
        ha_url="http://localhost:8123",
    )
    return notifier


@pytest.mark.asyncio
async def test_notifier() -> None:
    notifier = setup_notifier()

    # Existing command
    payload = {
        "message": "command_suspend",
        "push_token": notifier.push_token,
        "registration_info": {
            "app_id": "halinuxcompanion-0.1.0",
            "app_version": "0.1.0",
            "webhook_id": "fd0e8af0183a1445e029436995286479a57d5a455b4d6ce3e40b743c3969b 505",
            "os_version": "6.5.9-arch2-1",
        },
    }
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    result = await notifier.on_ha_notification(request)
    assert result is not None

    # Non existing command
    payload = {
        "message": "suspend",
        "push_token": notifier.push_token,
        "registration_info": {
            "app_id": "halinuxcompanion-0.1.0",
            "app_version": "0.1.0",
            "webhook_id": "fd0e8af0183a1445e029436995286479a57d5a455b4d6ce3e40b743c3969b 505",
            "os_version": "6.5.9-arch2-1",
        },
    }
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    result = await notifier.on_ha_notification(request)
    assert result is not None


def test_companion_init() -> None:
    companion = setup_companion()
    assert companion is not None
