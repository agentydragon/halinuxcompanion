"""OAuth registration flow for Home Assistant."""

import asyncio
import logging
import secrets
import webbrowser
from urllib.parse import urlencode, urlparse, urlunparse

import aiohttp
from aiohttp import web

from halinuxcompanion.api.models import DeviceRegistration, Registration
from halinuxcompanion.storage import save_registration

logger = logging.getLogger(__name__)

OAUTH_CALLBACK_PORT = 8765
OAUTH_CALLBACK_PATH = "/auth/callback"


class OAuthHandler:
    """Handles OAuth flow for Home Assistant registration."""

    def __init__(self, instance_url: str):
        """Initialize OAuth handler.

        Args:
            instance_url: The Home Assistant instance URL.
        """
        self.instance_url = instance_url.rstrip("/")
        self._future: asyncio.Future[str] = asyncio.Future()

    async def handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback from Home Assistant.

        Args:
            request: The callback request.

        Returns:
            HTML response to show to the user.
        """
        if "error" in request.query:
            error_msg = request.query.get("error_description", "Unknown error")
            self._future.set_exception(RuntimeError(f"OAuth error: {error_msg}"))
            return web.Response(
                text=f"<html><body><h1>Error</h1><p>Authentication failed: {error_msg}</p><p>You can close this window.</p></body></html>",
                content_type="text/html",
            )

        auth_code = request.query.get("code")
        if not auth_code:
            self._future.set_exception(RuntimeError("No authorization code received"))
            return web.Response(
                text="<html><body><h1>Error</h1><p>No authorization code received</p><p>You can close this window.</p></body></html>",
                content_type="text/html",
            )

        self._future.set_result(auth_code)
        return web.Response(
            text="<html><body><h1>Success!</h1><p>Authentication successful. You can close this window.</p></body></html>",
            content_type="text/html",
        )

    async def wait_for_auth(self) -> str:
        """Wait for authentication to complete.

        Returns:
            The authorization code.

        Raises:
            RuntimeError: If authentication fails.
        """
        return await self._future


async def register_device(instance_url: str, device_name: str) -> Registration:
    """Register this device with Home Assistant.

    Args:
        instance_url: The Home Assistant instance URL.
        device_name: The name for this device.

    Returns:
        The registration data.

    Raises:
        RuntimeError: If registration fails.
    """
    instance_url = instance_url.rstrip("/")

    # Start OAuth flow
    handler = OAuthHandler(instance_url)

    # Create web app for callback
    app = web.Application()
    app.router.add_get(OAUTH_CALLBACK_PATH, handler.handle_callback)

    # Start server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", OAUTH_CALLBACK_PORT)
    await site.start()

    # Build OAuth URL
    callback_url = f"http://localhost:{OAUTH_CALLBACK_PORT}{OAUTH_CALLBACK_PATH}"
    auth_url = f"{instance_url}/auth/authorize?" + urlencode(
        {
            "client_id": callback_url,
            "redirect_uri": callback_url,
            # Generate state for CSRF protection
            "state": secrets.token_urlsafe(32),
        }
    )

    # Open browser
    logger.info(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    try:
        # Wait for callback
        logger.info("Waiting for authentication...")
        auth_code = await handler.wait_for_auth()

        # Exchange code for token
        # Don't follow redirects automatically to handle HTTP->HTTPS redirects properly
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(force_close=True)) as session:
            token_data = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "client_id": callback_url,
            }

            # Try the token endpoint, allowing redirects
            token_url = f"{instance_url}/auth/token"

            async with session.post(
                token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True,
            ) as resp:
                resp.raise_for_status()
                token_response = await resp.json()

                # Update instance_url if we were redirected (e.g., HTTP->HTTPS)
                if str(resp.url) != token_url:
                    parsed = urlparse(str(resp.url))
                    instance_url = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
                    logger.info(f"Updated instance URL after redirect: {instance_url}")

            access_token = token_response["access_token"]
            logger.info("Successfully obtained access token")

            # Register device
            device = DeviceRegistration(device_name=device_name)
            logger.info(f"Registering device with data: {device}")

            registration_url = f"{instance_url}/api/mobile_app/registrations"
            logger.info(f"Sending registration request to: {registration_url}")

            async with session.post(
                registration_url,
                json=device.model_dump(),
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status not in (200, 201):  # 200 OK or 201 Created
                    error_text = await resp.text()
                    logger.error(f"Registration failed with status {resp.status}: {error_text}")
                    resp.raise_for_status()
                reg_data = await resp.json()
                logger.info(f"Registration response: {reg_data}")

            # Create registration object combining response with instance URL
            registration = Registration(
                **reg_data,
                instance_url=instance_url,
            )

            # Save to keyring
            save_registration(registration)

            logger.info("Registration successful!")
            return registration

    finally:
        await runner.cleanup()
