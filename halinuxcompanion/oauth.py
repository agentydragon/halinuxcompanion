import asyncio
import ipaddress
import logging
import secrets
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlparse, urlunparse

from aiohttp import ClientSession, web
from pydantic import BaseModel

if TYPE_CHECKING:
    from .secrets import SecretStorage


logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when OAuth authentication fails."""

    pass


def is_url_using_ip(url: str) -> bool:
    """Check if a URL is using an IP address instead of a domain name."""
    parsed = urlparse(url)
    if not (hostname := parsed.hostname):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # Not an IP address, it's a domain
        return False
    # Allow loopback and private IPs.
    return not (ip.is_loopback or ip.is_private)


class OAuthTokens(BaseModel):
    """Model for OAuth token storage - matches Home Assistant OAuth response.

    Fields match the OAuth token response from Home Assistant:
    - access_token: The access token to use for API requests
    - refresh_token: Token to refresh access when it expires
    - expires_in: Seconds until token expires (from server response)
    - token_type: Usually "Bearer"

    Additional fields added by us:
    - expires_at: absolute expiry time calculated from expires_in
    """

    access_token: str
    refresh_token: str
    expires_in: int  # Keep as int to match server response
    token_type: str  # Usually "Bearer"
    expires_at: datetime  # Added field for absolute expiry time

    # Extras seen, not handled: {"ha_auth_provider": "homeassistant"}

    @property
    def is_expired(self) -> bool:
        """Check if token has actually expired."""
        return datetime.now() >= self.expires_at

    @property
    def expires_soon(self) -> bool:
        """Check if token expires within the next 60 seconds."""
        return datetime.now() >= self.expires_at - timedelta(seconds=60)


@dataclass
class OAuthFlow:
    """Handles exactly one OAuth2 authentication flow with Home Assistant.

    Each instance represents a single OAuth flow with its own unique state token.
    The state is generated at initialization and cannot be changed.
    """

    ha_url: str
    redirect_host: str = "localhost"
    state: str = field(init=False)  # Always set, generated in __post_init__
    _auth_code_future: asyncio.Future[str] = field(init=False)

    def __post_init__(self):
        self.ha_url = self.ha_url.rstrip("/")
        # Generate state token once at initialization
        self.state = secrets.token_urlsafe(32)
        # Create future for auth code
        self._auth_code_future = asyncio.get_event_loop().create_future()
        self.redirect_port = 9736

    @property
    def redirect_uri(self) -> str:
        """Build the OAuth callback URI with the given port."""
        return f"http://localhost:{self.redirect_port}/auth/callback"

    @property
    def client_id(self) -> str:
        """Return the client ID for OAuth requests."""
        return f"http://localhost:{self.redirect_port}"

    @property
    def authorization_url(self) -> str:
        # Parse the base URL and add our path and query
        base = urlparse(self.ha_url)
        return urlunparse(
            (
                base.scheme,
                base.netloc,
                "/auth/authorize",
                "",
                urlencode(
                    {
                        "response_type": "code",
                        "client_id": self.client_id,
                        "redirect_uri": self.redirect_uri,
                        "state": self.state,
                    }
                ),
                "",
            )
        )

    def _make_html_response(self, title: str, message: str) -> web.Response:
        """Create an HTML response page."""
        html = f"""<html>
<head><title>{title}</title></head>
<body>
    <h1>{title}</h1>
    <p>{message}</p>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_callback(
        self, request: web.Request, auth_code_future: asyncio.Future[str]
    ) -> web.Response:
        """Handle the OAuth callback from Home Assistant."""
        try:
            code = request.query.get("code")
            state = request.query.get("state")

            if not (code and state):
                error_msg = request.query.get("error", "Unknown error")
                if error_desc := request.query.get("error_description", ""):
                    error_msg += f" - {error_desc}"
                raise AuthenticationError(error_msg)

            if state != self.state:
                raise AuthenticationError(
                    f"State mismatch in OAuth callback. Expected: {self.state}, Got: {state}"
                )

            # Set the auth code in the future
            auth_code_future.set_result(code)
            return self._make_html_response(
                "Authentication successful!", "You can close this window now."
            )

        except AuthenticationError as e:
            logger.error(str(e))
            auth_code_future.set_exception(e)
            return self._make_html_response("Authentication failed", str(e))

    async def _request_token(self, session: ClientSession, operation: str, data: dict):
        """Common method to request tokens from Home Assistant."""
        async with session.post(
            f"{self.ha_url}/auth/token",
            data=data | {"client_id": self.client_id},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != 200:
                raise AuthenticationError(
                    f"Token {operation} failed: {resp.status} - {await resp.text()}"
                )

            token_data = await resp.json()
        expires_delta = timedelta(seconds=token_data["expires_in"])
        token_data["expires_at"] = (expires_at := datetime.now() + expires_delta)

        logger.info(
            f"Token {operation} successful, expires at {expires_at.isoformat()} "
            f"({expires_delta} from now)"
        )
        return token_data

    async def exchange_code_for_token(
        self, session: ClientSession, auth_code: str
    ) -> OAuthTokens:
        """Exchange the authorization code for access and refresh tokens."""
        return OAuthTokens.model_validate(
            await self._request_token(
                session,
                "exchange",
                {
                    "grant_type": "authorization_code",
                    "code": auth_code,
                },
            )
        )

    async def refresh_access_token(
        self, session: ClientSession, refresh_token: str
    ) -> OAuthTokens:
        """Refresh the access token using the refresh token."""
        refreshed = await self._request_token(
            session,
            "refresh",
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        # Refresh response does not include refresh_token, so we need to keep it
        return OAuthTokens(refresh_token=refresh_token, **refreshed)

    async def run(self, storage: "SecretStorage") -> None:
        """Run the complete OAuth authentication flow.

        Args:
            storage: Secret storage backend to save tokens
        """
        print(f"Starting OAuth authentication flow with {self.ha_url}")
        # Check if using IP address for OAuth
        if is_url_using_ip(self.ha_url):
            raise AuthenticationError(
                "OAuth authentication requires using a domain name, not an IP address.\n"
                "Home Assistant only allows OAuth with IP addresses for local/private networks.\n"
                "Options:\n"
                "1. Use a domain name for your Home Assistant instance\n"
                "2. Add an entry to /etc/hosts (e.g., '10.13.13.100 homeassistant.local')\n"
                "3. Use a long-lived access token instead of OAuth\n"
                "See: https://www.home-assistant.io/docs/authentication/#error-invalid-client-id-or-redirect-url"
            )

        # Set up temporary web server for callback
        app = web.Application()
        auth_code_future = asyncio.get_event_loop().create_future()
        app.router.add_get(
            "/auth/callback",
            partial(self.handle_callback, auth_code_future=auth_code_future),
        )

        logger.info(f"Starting OAuth callback server on port {self.redirect_port}")

        runner = web.AppRunner(app)
        await runner.setup()
        try:
            await web.TCPSite(runner, self.redirect_host, self.redirect_port).start()

            print("\nOpening browser for authentication...")
            print(f"If browser doesn't open, please visit: {self.authorization_url}\n")
            webbrowser.open(self.authorization_url)

            # Wait for auth code from callback
            auth_code = await auth_code_future
        finally:
            await runner.cleanup()

        # Exchange code for tokens
        async with ClientSession() as session:
            # Save tokens using the storage backend
            tokens = await self.exchange_code_for_token(session, auth_code)
            storage.save_oauth_tokens(tokens)

        print("\nAuthentication successful! Tokens saved.")


async def ensure_valid_oauth_token(
    oauth_tokens: OAuthTokens,
    session: ClientSession,
    ha_url: str,
    storage: "SecretStorage",
) -> OAuthTokens:
    """Ensure we have a valid OAuth access token, refreshing if needed.

    Args:
        oauth_tokens: Current OAuth tokens
        session: Active client session
        ha_url: Home Assistant URL
        storage: Secret storage backend

    Returns:
        Updated OAuth tokens if successful

    Raises:
        AuthenticationError: If token refresh fails (requires user re-authentication)
    """
    # If token is still valid, return as-is
    if not oauth_tokens.expires_soon:
        return oauth_tokens

    # Try to refresh
    logger.info("Access token expired, attempting to refresh...")
    try:
        new_tokens = await OAuthFlow(ha_url).refresh_access_token(
            session, oauth_tokens.refresh_token
        )
    except AuthenticationError:
        raise AuthenticationError(
            "OAuth token refresh failed.\n"
            "Your authentication has expired. Please re-authenticate:\n"
            "Run: halinuxcompanion --oauth"
        )
    storage.save_oauth_tokens(new_tokens)
    logger.info("OAuth token refreshed successfully")
    return new_tokens
