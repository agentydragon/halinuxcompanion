"""Unit tests for OAuth/Server integration."""

import asyncio

import pytest
from aiohttp import ClientSession

from halinuxcompanion.api import Server
from halinuxcompanion.oauth import AuthenticationError

# These are integration tests that require real sockets
pytestmark = [pytest.mark.asyncio, pytest.mark.requires_hardware]


async def test_oauth_callback_no_active_flow() -> None:
    """Test OAuth callback returns proper error when no flow is active."""
    server = Server("localhost", 0)  # Use port 0 for automatic assignment

    async with server:
        # Get the actual port assigned
        port = server.port

        # Hit the callback URL without an active OAuth flow
        async with (
            ClientSession() as session,
            session.get(f"http://localhost:{port}/auth/callback?code=test&state=test") as resp,
        ):
            text = await resp.text()
            assert resp.status == 400
            assert "No OAuth Flow Active" in text
            assert "OAuth flow timed out" in text


async def test_oauth_flow_success() -> None:
    """Test successful OAuth flow."""
    server = Server("localhost", 0)

    async with server:
        port = server.port

        # Start OAuth flow
        oauth_task = asyncio.create_task(server.run_oauth_flow(state="test_state_success"))

        # Wait a moment for setup
        await asyncio.sleep(0.1)

        # Simulate successful callback
        async with (
            ClientSession() as session,
            session.get(f"http://localhost:{port}/auth/callback?code=auth_code_123&state=test_state_success") as resp,
        ):
            text = await resp.text()
            assert resp.status == 200
            assert "Authentication Successful" in text
            assert "You can now close this window" in text

        # Verify the OAuth flow completes successfully
        result = await oauth_task
        assert result == {"code": "auth_code_123", "state": "test_state_success"}


async def test_oauth_state_mismatch() -> None:
    """Test OAuth flow with state mismatch."""
    server = Server("localhost", 0)

    async with server:
        port = server.port

        # Start OAuth flow
        oauth_task = asyncio.create_task(server.run_oauth_flow(state="expected_state"))

        await asyncio.sleep(0.1)

        # Send callback with wrong state
        async with (
            ClientSession() as session,
            session.get(f"http://localhost:{port}/auth/callback?code=test_code&state=wrong_state") as resp,
        ):
            text = await resp.text()
            assert resp.status == 400
            assert "Invalid OAuth State" in text
            assert "expected expected_state, got wrong_state" in text

        # Verify the OAuth flow fails with proper error
        with pytest.raises(AuthenticationError) as exc_info:
            await oauth_task
        assert "State mismatch" in str(exc_info.value)


async def test_oauth_error_from_ha() -> None:
    """Test OAuth flow when Home Assistant returns an error."""
    server = Server("localhost", 0)

    async with server:
        port = server.port

        # Start OAuth flow
        oauth_task = asyncio.create_task(server.run_oauth_flow(state="test_state_error"))

        await asyncio.sleep(0.1)

        # Send callback with error
        async with (
            ClientSession() as session,
            session.get(
                f"http://localhost:{port}/auth/callback"
                f"?error=access_denied&error_description=User+denied+access"
                f"&state=test_state_error"
            ) as resp,
        ):
            text = await resp.text()
            assert resp.status == 400
            assert "Authentication Failed" in text
            assert "User denied access" in text

        # Verify the OAuth flow fails
        with pytest.raises(AuthenticationError) as exc_info:
            await oauth_task
        assert "OAuth error: User denied access" in str(exc_info.value)


async def test_oauth_no_code_provided() -> None:
    """Test OAuth callback without authorization code."""
    server = Server("localhost", 0)

    async with server:
        port = server.port

        # Start OAuth flow
        oauth_task = asyncio.create_task(server.run_oauth_flow(state="test_state_no_code"))

        await asyncio.sleep(0.1)

        # Send callback without code
        async with (
            ClientSession() as session,
            session.get(f"http://localhost:{port}/auth/callback?state=test_state_no_code") as resp,
        ):
            text = await resp.text()
            assert resp.status == 400
            assert "No Authorization Code" in text

        # Verify the OAuth flow fails
        with pytest.raises(AuthenticationError) as exc_info:
            await oauth_task
        assert "No authorization code received" in str(exc_info.value)


async def test_oauth_flow_already_active() -> None:
    """Test that only one OAuth flow can be active at a time."""
    server = Server("localhost", 0)

    async with server:
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
