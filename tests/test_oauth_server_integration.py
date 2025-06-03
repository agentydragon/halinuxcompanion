"""Unit tests for OAuth/Server integration."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from urllib.parse import urlencode

import pytest
from aiohttp import ClientResponse, ClientSession

from halinuxcompanion.api import Server
from halinuxcompanion.oauth import AuthenticationError

# These are integration tests that require real sockets
pytestmark = [pytest.mark.asyncio, pytest.mark.requires_hardware, pytest.mark.usefixtures("socket_enabled")]


@pytest.fixture
def event_loop():
    """Provide event loop fixture for compatibility with homeassistant pytest plugin."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def server(unused_tcp_port: int) -> AsyncGenerator[Server, None]:
    """Create a test server with an unused port."""
    server = Server("localhost", unused_tcp_port)
    async with server:
        yield server


@pytest.fixture
async def http_session() -> AsyncGenerator[ClientSession, None]:
    """Create an HTTP client session."""
    async with ClientSession() as session:
        yield session


@pytest.fixture
def make_oauth_request(
    http_session: ClientSession, server: Server
) -> Callable[[dict[str, str]], Awaitable[ClientResponse]]:
    """Create a function to make OAuth callback requests."""

    async def _make_request(params: dict[str, str]) -> ClientResponse:
        url = f"http://localhost:{server.port}/auth/callback?{urlencode(params)}"
        return await http_session.get(url)

    return _make_request


async def test_oauth_callback_no_active_flow(
    server: Server, make_oauth_request: Callable[[dict[str, str]], Awaitable[ClientResponse]]
) -> None:
    """Test OAuth callback returns proper error when no flow is active."""
    # Hit the callback URL without an active OAuth flow
    async with await make_oauth_request({"code": "test", "state": "test"}) as resp:
        text = await resp.text()
        assert resp.status == 400
        assert "No OAuth Flow Active" in text
        assert "OAuth flow timed out" in text


async def test_oauth_flow_success(
    server: Server, make_oauth_request: Callable[[dict[str, str]], Awaitable[ClientResponse]]
) -> None:
    """Test successful OAuth flow."""
    # Start OAuth flow
    oauth_task = asyncio.create_task(server.run_oauth_flow(state="test_state_success"))

    # Wait a moment for setup
    await asyncio.sleep(0.1)

    # Simulate successful callback
    async with await make_oauth_request({"code": "auth_code_123", "state": "test_state_success"}) as resp:
        text = await resp.text()
        assert resp.status == 200
        assert "Authentication Successful" in text
        assert "You can now close this window" in text

    # Verify the OAuth flow completes successfully
    result = await oauth_task
    assert result == {"code": "auth_code_123", "state": "test_state_success"}


async def test_oauth_state_mismatch(
    server: Server, make_oauth_request: Callable[[dict[str, str]], Awaitable[ClientResponse]]
) -> None:
    """Test OAuth flow with state mismatch."""
    # Start OAuth flow
    oauth_task = asyncio.create_task(server.run_oauth_flow(state="expected_state"))

    await asyncio.sleep(0.1)

    # Send callback with wrong state
    async with await make_oauth_request({"code": "test_code", "state": "wrong_state"}) as resp:
        text = await resp.text()
        assert resp.status == 400
        assert "Invalid OAuth State" in text
        assert "expected expected_state, got wrong_state" in text

    # Verify the OAuth flow fails with proper error
    with pytest.raises(AuthenticationError) as exc_info:
        await oauth_task
    assert "State mismatch" in str(exc_info.value)


async def test_oauth_error_from_ha(
    server: Server, make_oauth_request: Callable[[dict[str, str]], Awaitable[ClientResponse]]
) -> None:
    """Test OAuth flow when Home Assistant returns an error."""
    # Start OAuth flow
    oauth_task = asyncio.create_task(server.run_oauth_flow(state="test_state_error"))

    await asyncio.sleep(0.1)

    # Send callback with error
    async with await make_oauth_request(
        {"error": "access_denied", "error_description": "User denied access", "state": "test_state_error"}
    ) as resp:
        text = await resp.text()
        assert resp.status == 400
        assert "Authentication Failed" in text
        assert "User denied access" in text

    # Verify the OAuth flow fails
    with pytest.raises(AuthenticationError) as exc_info:
        await oauth_task
    assert "OAuth error: User denied access" in str(exc_info.value)


async def test_oauth_no_code_provided(
    server: Server, make_oauth_request: Callable[[dict[str, str]], Awaitable[ClientResponse]]
) -> None:
    """Test OAuth callback without authorization code."""
    # Start OAuth flow
    oauth_task = asyncio.create_task(server.run_oauth_flow(state="test_state_no_code"))

    await asyncio.sleep(0.1)

    # Send callback without code
    async with await make_oauth_request({"state": "test_state_no_code"}) as resp:
        text = await resp.text()
        assert resp.status == 400
        assert "No Authorization Code" in text

    # Verify the OAuth flow fails
    with pytest.raises(AuthenticationError) as exc_info:
        await oauth_task
    assert "No authorization code received" in str(exc_info.value)


async def test_oauth_flow_already_active(server: Server) -> None:
    """Test that only one OAuth flow can be active at a time."""
    # Start first OAuth flow
    oauth_task1 = asyncio.create_task(server.run_oauth_flow(state="state1"))

    await asyncio.sleep(0.1)

    # Try to start second OAuth flow
    with pytest.raises(RuntimeError) as exc_info:
        await server.run_oauth_flow(state="state2")
    assert "OAuth flow already in progress" in str(exc_info.value)

    # Cancel the first task to clean up
    oauth_task1.cancel()
    try:
        await oauth_task1
    except asyncio.CancelledError:
        pass
