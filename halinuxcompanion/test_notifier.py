"""Unit tests for the notifier module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError, web
from hamcrest import assert_that, contains_exactly, has_entries

from halinuxcompanion.api import API, Server
from halinuxcompanion.companion import CommandConfig
from halinuxcompanion.dbus import Dbus
from halinuxcompanion.notifier import NotificationRequest, NotificationRequestData, Notifier

PUSH_TOKEN = "test-push-token"
HA_URL = "http://localhost:8123"


@pytest.fixture
def mock_api():
    """Create a mock API instance."""
    api = MagicMock(spec=API)
    api.post = AsyncMock(return_value=MagicMock(status=200))
    return api


@pytest.fixture
def mock_server():
    """Create a mock Server instance."""
    server = MagicMock(spec=Server)
    server.set_notification_handler = MagicMock()
    return server


@pytest.fixture
def mock_dbus_interface():
    """Create a mock DBus interface."""
    interface = MagicMock()
    interface.call_notify = AsyncMock(return_value=123)  # Mock notification ID
    interface.on_action_invoked = MagicMock()
    interface.on_notification_closed = MagicMock()
    return interface


@pytest.fixture
async def notifier_with_dbus(mock_api, mock_server, mock_dbus_interface):
    """Create a Notifier instance with DBus interface setup."""
    notifier = Notifier(
        api=mock_api,
        server=mock_server,
        push_token=PUSH_TOKEN,
        url_program="xdg-open",
        commands={},
        ha_url=HA_URL,
    )

    mock_dbus = MagicMock(spec=Dbus)
    mock_dbus.get_interface = AsyncMock(return_value=mock_dbus_interface)

    await notifier.setup_dbus(mock_dbus)
    notifier.interface = mock_dbus_interface
    return notifier


@pytest.fixture
def mock_subprocess():
    with patch("halinuxcompanion.notifier.run_subprocess_with_logging") as mock:
        yield mock


@pytest.fixture
async def client(aiohttp_client, notifier_with_dbus):
    """Create test HTTP client."""
    app = web.Application()
    app.router.add_post("/notify", notifier_with_dbus.on_ha_notification)
    return await aiohttp_client(app)


@pytest.mark.usefixtures("socket_enabled")
class TestNotificationAPI:
    """Test notification API endpoints."""

    async def test_notifier_existing_command(self, client, notifier_with_dbus):
        """Test notifier handles existing command correctly."""
        # Add a command
        notifier_with_dbus.commands["greet"] = CommandConfig(name="greet", command=["echo", "Hello"])

        resp = await client.post("/notify", json={"message": "command_greet", "push_token": PUSH_TOKEN})
        assert resp.status == 200
        data = await resp.json()
        assert_that(data, has_entries(success=True))

    async def test_notifier_non_existing_command(self, client):
        """Test notifier handles non-existing command correctly."""
        resp = await client.post("/notify", json={"message": "command_unknown", "push_token": PUSH_TOKEN})
        assert resp.status == 404
        data = await resp.json()
        assert_that(data, has_entries(error="command_not_found"))

    async def test_notifier_wrong_push_token(self, client):
        resp = await client.post("/notify", json={"message": "Test", "push_token": "wrong"})
        assert resp.status == 400
        data = await resp.json()
        assert_that(data, has_entries(error="push_token_mismatch"))

    async def test_notifier_invalid_json(self, client):
        """Test notifier handles invalid JSON payload."""
        resp = await client.post("/notify", data="{ invalid json", headers={"Content-Type": "application/json"})
        assert resp.status == 400
        data = await resp.json()
        assert_that(data, has_entries(error="invalid_json"))


@pytest.mark.usefixtures("socket_enabled")
class TestNotificationTypes:
    """Test different types of notifications."""

    async def test_basic_notification(self, client, notifier_with_dbus):
        """Test basic notification with just title and message."""
        resp = await client.post(
            "/notify",
            json={"push_token": PUSH_TOKEN, "title": "Title", "message": "Message body"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert_that(data, has_entries(success=True))

        # Verify DBus call
        notifier_with_dbus.interface.call_notify.assert_called_once()
        args = notifier_with_dbus.interface.call_notify.call_args[0]
        assert args[3] == "Title"
        assert args[4] == "Message body"

    async def test_notification_with_default_title(self, client, notifier_with_dbus):
        """Test notification uses default title when not provided."""
        resp = await client.post("/notify", json={"push_token": PUSH_TOKEN, "message": "Message"})
        assert resp.status == 201

        # Verify default title is used
        args = notifier_with_dbus.interface.call_notify.call_args[0]
        assert args[3] == "Home Assistant"  # Default title

    async def test_notification_with_tag_replacement(self, client, notifier_with_dbus):
        """Test notification replacement using tags."""
        # First notification
        notifier_with_dbus.interface.call_notify.return_value = 123
        resp1 = await client.post(
            "/notify",
            json={
                "push_token": PUSH_TOKEN,
                "title": "First",
                "data": {"tag": "update-tag"},
            },
        )
        assert resp1.status == 201

        # Verify tag mapping
        assert notifier_with_dbus.tagtoid["update-tag"] == 123

        # Second notification replacing first
        notifier_with_dbus.interface.call_notify.return_value = 124
        resp2 = await client.post(
            "/notify",
            json={
                "push_token": PUSH_TOKEN,
                "title": "Second",
                "data": {"tag": "update-tag"},
            },
        )
        assert resp2.status == 201

        # Verify replacement ID was passed
        second_call_args = notifier_with_dbus.interface.call_notify.call_args[0]
        assert second_call_args[1] == 123  # replaces_id

        # Verify history was updated
        assert_that(notifier_with_dbus.history.keys(), contains_exactly(124))
        assert notifier_with_dbus.tagtoid["update-tag"] == 124

    async def test_clear_notification(self, client, notifier_with_dbus):
        """Test clear_notification message sets minimal timeout."""
        resp = await client.post(
            "/notify",
            json={"push_token": PUSH_TOKEN, "message": "clear_notification", "data": {"tag": "clear-me"}},
        )
        assert resp.status == 201

        # Verify timeout is 1ms for clear
        args = notifier_with_dbus.interface.call_notify.call_args[0]
        assert args[7] == 1  # expire_timeout

    async def test_notification_with_custom_timeout(self, client, notifier_with_dbus):
        """Test notification with custom timeout."""
        resp = await client.post(
            "/notify",
            json={"push_token": PUSH_TOKEN, "message": "Timed notification", "data": {"timeout": 5.5}},
        )
        assert resp.status == 201

        # Verify timeout conversion to milliseconds
        args = notifier_with_dbus.interface.call_notify.call_args[0]
        assert args[7] == 5500  # 5.5 seconds = 5500ms

    async def test_notification_with_invalid_timeout(self, client):
        """Test notification with invalid timeout is rejected by validation."""
        resp = await client.post(
            "/notify",
            json={
                "push_token": PUSH_TOKEN,
                "message": "Bad timeout",
                "data": {"timeout": "not-a-number"},
            },
        )
        # Pydantic validation should reject non-numeric timeout
        assert resp.status == 400
        data = await resp.json()
        assert_that(data, has_entries(error="invalid_data"))


@pytest.fixture
async def sent_notification_with_actions(client, notifier_with_dbus):
    resp = await client.post(
        "/notify",
        json={
            "push_token": PUSH_TOKEN,
            "message": "Choose an action",
            "data": {
                "actions": [
                    {"action": "yes", "title": "Yes"},
                    {"action": "no", "title": "No"},
                    {"action": "maybe", "title": "Maybe", "uri": "http://example.com"},
                ]
            },
        },
    )
    assert resp.status == 201

    # Verify actions format for D-Bus
    actions = notifier_with_dbus.interface.call_notify.call_args[0][5]  # actions list
    assert actions == ["default", "Default", "yes", "Yes", "no", "No", "maybe", "Maybe"]


@pytest.mark.usefixtures("socket_enabled")
class TestNotificationActions:
    """Test notification actions."""

    async def test_notification_with_actions(self, sent_notification_with_actions, notifier_with_dbus, mock_subprocess):
        """Test notification with multiple actions."""

        await notifier_with_dbus.on_action(123, "maybe")

        # Verify HA event was triggered
        notifier_with_dbus.api.post.assert_called_once()
        call_args = notifier_with_dbus.api.post.call_args
        assert call_args[0][0] == "/api/events/mobile_app_notification_action"
        assert call_args[1]["json"]["action"] == "maybe"

        # Verify URI was opened
        mock_subprocess.assert_called_once()
        assert mock_subprocess.call_args[0][0] == ["xdg-open", "http://example.com"]

    async def test_action_no_url_program(self, notifier_with_dbus, sent_notification_with_actions):
        """Test action with URL but no url_program configured."""
        notifier_with_dbus.url_program = None  # Disable URL program

        # Should not crash
        await notifier_with_dbus.on_action(123, "maybe")

    async def test_notification_closed_event(self, notifier_with_dbus, sent_notification_with_actions):
        """Test notification close triggers HA event."""

        await notifier_with_dbus.on_close(123, "dismissed")  # Simulate close event

        # Verify HA event
        notifier_with_dbus.api.post.assert_called_once()
        call_args = notifier_with_dbus.api.post.call_args
        assert call_args[0][0] == "/api/events/mobile_app_notification_cleared"

        # Verify notification was removed from history
        assert 205 not in notifier_with_dbus.history

    @patch("halinuxcompanion.notifier.run_subprocess_with_logging")
    async def test_action_invoked_default(self, mock_subprocess, notifier_with_dbus):
        """Test default action opens URL."""
        # Setup notification in history
        notifier_with_dbus.history[123] = NotificationRequest(
            message="Click me", data=NotificationRequestData(url="https://example.com")
        )

        await notifier_with_dbus.on_action(123, "default")

        # Verify URL was opened
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0]
        assert args[0] == ["xdg-open", "https://example.com"]

    async def test_action_lovelace_url(self, mock_subprocess, notifier_with_dbus):
        """Test lovelace URLs are prefixed with HA URL."""
        notif = NotificationRequest(
            message="View dashboard",
            data=NotificationRequestData(clickAction="/lovelace/default"),
        )
        notifier_with_dbus.history[203] = notif

        await notifier_with_dbus.on_action(203, "default")

        # Verify URL was prefixed
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0]
        assert args[0] == ["xdg-open", "http://localhost:8123/lovelace/default"]

    async def test_action_no_action_url(self, mock_subprocess, notifier_with_dbus):
        """Test noAction URL is not opened."""
        notifier_with_dbus.history[123] = NotificationRequest(
            message="Do nothing", data=NotificationRequestData(url="noAction")
        )

        await notifier_with_dbus.on_action(123, "default")

        # Verify no subprocess was called
        mock_subprocess.assert_not_called()


class TestURLValidation:
    """Test URL scheme validation for security."""

    @pytest.mark.parametrize("url", ["https://example.com", "http://example.com"])
    async def test_url_scheme_ok(self, mock_subprocess, notifier_with_dbus, url):
        """Test safe URL schemes are opened."""
        notifier_with_dbus.history[123] = NotificationRequest(data=NotificationRequestData(url=url))
        await notifier_with_dbus.on_action(123, "default")
        mock_subprocess.assert_called_once()

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",  # Security risk
            "javascript:alert('xss')",  # XSS risk
            "data:text/html,<script>alert('xss')</script>",  # Data URL risk
            "",  # Empty
            "noAction",  # Special no-action URL
        ],
    )
    async def test_url_scheme_noop(self, mock_subprocess, notifier_with_dbus, url):
        """Test unsafe/noop URLs schemes are not opened."""
        notifier_with_dbus.history[123] = NotificationRequest(data=NotificationRequestData(url=url))
        await notifier_with_dbus.on_action(123, "default")
        mock_subprocess.assert_not_called()


class TestErrorHandling:
    """Test error handling in notification system."""

    async def test_ha_event_error_handling(self, notifier_with_dbus):
        """Test HA event errors don't crash notification handling."""
        # Make API post raise an exception
        notifier_with_dbus.api.post.side_effect = ClientError("Connection failed")
        notifier_with_dbus.history[123] = NotificationRequest(message="Will fail")

        await notifier_with_dbus.on_close(123, "expired")  # Should not raise

        # Notification should still be removed
        assert 123 not in notifier_with_dbus.history
