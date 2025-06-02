from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from aiohttp import web

from halinuxcompanion.companion import CommandConfig, Companion, CompanionConfig, NotificationServiceConfig
from halinuxcompanion.module_config import ModulesConfig
from halinuxcompanion.notifier import Notifier
from halinuxcompanion.secret_storage import SecretStorageBackend

if TYPE_CHECKING:
    from aiohttp.test_utils import TestClient


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


def create_notifier_app() -> tuple[web.Application, Notifier]:
    """Create an aiohttp app with notifier routes for testing."""
    # Create mock dependencies
    mock_api = MagicMock()
    mock_server = MagicMock()

    notifier = Notifier(
        api=mock_api,
        server=mock_server,
        push_token="d0f7bd90-7b23-11ee-852f-00d861ab3a9c",
        url_program="xdg-open",
        commands={
            "command_suspend": CommandConfig(name="Suspend", command=["ls"]),
        },
        ha_url="http://localhost:8123",
    )

    app = web.Application()
    app.router.add_post("/notify", notifier.on_ha_notification)

    return app, notifier


async def test_notifier_existing_command(aiohttp_client) -> None:
    """Test notifier handles existing command correctly."""
    app, notifier = create_notifier_app()
    client = await aiohttp_client(app)

    payload = {
        "message": "command_suspend",
        "push_token": notifier.push_token,
        "registration_info": {
            "app_id": "halinuxcompanion-0.1.0",
            "app_version": "0.1.0",
            "webhook_id": "test-webhook-id",
            "os_version": "6.5.9-arch2-1",
        },
    }

    resp = await client.post("/notify", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data is not None


async def test_notifier_non_existing_command(aiohttp_client) -> None:
    """Test notifier handles non-existing command correctly."""
    app, notifier = create_notifier_app()
    client: TestClient = await aiohttp_client(app)

    payload = {
        "message": "suspend",
        "push_token": notifier.push_token,
        "registration_info": {
            "app_id": "halinuxcompanion-0.1.0",
            "app_version": "0.1.0",
            "webhook_id": "test-webhook-id",
            "os_version": "6.5.9-arch2-1",
        },
    }

    resp = await client.post("/notify", json=payload)
    assert resp.status == 200
    data = await resp.json()
    assert data is not None


async def test_notifier_wrong_push_token(aiohttp_client) -> None:
    """Test notifier returns 404 for wrong push token to avoid information leakage."""
    app, notifier = create_notifier_app()
    client: TestClient = await aiohttp_client(app)

    payload = {
        "message": "Test notification",
        "push_token": "wrong_token_12345",
        "registration_info": {
            "app_id": "halinuxcompanion-0.1.0",
            "app_version": "0.1.0",
            "webhook_id": "test-webhook-id",
            "os_version": "6.5.9-arch2-1",
        },
    }

    resp = await client.post("/notify", json=payload)
    assert resp.status == 404
    data = await resp.json()
    assert data["error"] == "not_found"
    assert data["errorMessage"] == "Webhook not found"


def test_companion_init() -> None:
    companion = setup_companion()
    assert companion is not None
