import ipaddress
import logging
import secrets
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse, urlunparse

from aiohttp import ClientSession
from pydantic import BaseModel

from .constants import SC_OK

if TYPE_CHECKING:
    from .api import Server
    from .secret_storage import SecretStorage


logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when OAuth authentication fails."""


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
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def expires_soon(self) -> bool:
        """Check if token expires within the next 60 seconds."""
        return datetime.now(timezone.utc) >= self.expires_at - timedelta(seconds=60)


@dataclass
class OAuthFlow:
    """Handles exactly one OAuth2 authentication flow with Home Assistant.

    Each instance represents a single OAuth flow with its own unique state token.
    The state is generated at initialization and cannot be changed.
    """

    ha_url: str
    client_id: str
    redirect_uri: str
    # Generate state token once at initialization
    state: str = field(default_factory=lambda: secrets.token_urlsafe(32), init=False)

    async def _request_token(self, session: ClientSession, operation: str, data: dict) -> dict[str, Any]:
        """Common method to request tokens from Home Assistant."""
        async with session.post(
            f"{self.ha_url}/auth/token",
            data=data | {"client_id": self.client_id},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != SC_OK:
                raise AuthenticationError(f"Token {operation} failed: {resp.status} - {await resp.text()}")

            token_data = await resp.json()
        expires_delta = timedelta(seconds=token_data["expires_in"])
        token_data["expires_at"] = (expires_at := datetime.now(timezone.utc) + expires_delta)

        logger.info(f"Token {operation} successful, expires at {expires_at.isoformat()} ({expires_delta} from now)")
        return dict(token_data)

    async def refresh_access_token(self, session: ClientSession, refresh_token: str) -> OAuthTokens:
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

    async def run(self, storage: "SecretStorage", server: "Server", session: ClientSession) -> None:
        """Run the complete OAuth authentication flow using the unified server.

        Args:
            storage: Secret storage backend to save tokens
            server: The unified server instance
            session: aiohttp session for HTTP requests
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

        # Open browser
        print("\nOpening browser for authentication...")

        # Parse the base URL and add our path and query
        base = urlparse(self.ha_url)
        authorization_url = urlunparse(
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

        print(f"If browser doesn't open, please visit: {authorization_url}\n")
        webbrowser.open(authorization_url)

        # Use the server's integrated OAuth flow
        result = await server.run_oauth_flow(state=self.state)

        # Exchange the authorization code for access and refresh tokens.
        storage.oauth_tokens = OAuthTokens.model_validate(
            await self._request_token(
                session,
                "exchange",
                {
                    "grant_type": "authorization_code",
                    "code": result["code"],
                },
            )
        )
        print("\nAuthentication successful! Tokens saved.")
