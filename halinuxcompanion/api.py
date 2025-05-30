import logging
from typing import TYPE_CHECKING, Optional

from aiohttp import ClientResponse, ClientSession, web

from .companion import Companion
from .models import RegistrationData
from .oauth import AuthenticationError, OAuthTokens, ensure_valid_oauth_token

if TYPE_CHECKING:
    from .secrets import SecretStorage

logger = logging.getLogger(__name__)

SC_INVALID_JSON = 400
SC_UNAUTHORIZED = 401
SC_MOBILE_COMPONENT_NOT_LOADED = 404
SC_INTEGRATION_DELETED = 410
SESSION: Optional[ClientSession] = None


class API:
    """Class that handles Home Assisntat HTTP API calls"""

    token: str | None
    registration: RegistrationData | None = None
    session: ClientSession
    oauth_tokens: OAuthTokens | None = None
    companion: Companion

    def __init__(self, companion: Companion, storage: "SecretStorage") -> None:
        global SESSION
        if SESSION is None:
            SESSION = ClientSession()
        self.session = SESSION
        self.companion = companion
        self.storage = storage

        # Try authentication providers in order
        self.token = None
        self.oauth_tokens = None

        # Try long-lived token from config or storage
        self.token = companion.ha_token or storage.load_long_lived_token()
        if self.token:
            logger.info("Using long-lived access token")
        # Try OAuth tokens from storage
        elif oauth_tokens := storage.load_oauth_tokens():
            self.oauth_tokens = oauth_tokens
            logger.info("Using OAuth tokens from storage")
        else:
            # No authentication available - this is a fatal error
            raise AuthenticationError(
                "No authentication configured. Please provide one of:\n"
                "1. Long-lived access token in config file (ha_token)\n"
                "2. Run OAuth authentication: halinuxcompanion --oauth"
            )

    @property
    def headers(self) -> dict:
        """Get authorization headers based on current authentication."""
        token = self._get_valid_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        else:
            return {}

    def _get_valid_token(self) -> Optional[str]:
        """Get a valid access token from either long-lived token or OAuth."""
        # Prefer long-lived token
        if self.token:
            return self.token

        # Try OAuth token
        if self.oauth_tokens and not self.oauth_tokens.expires_soon:
            return self.oauth_tokens.access_token

        return None

    async def _ensure_authenticated(self) -> None:
        """Ensure we have valid authentication, refreshing OAuth token if needed.

        Raises:
            AuthenticationError: If authentication fails
        """
        # If we have a long-lived token, we're good
        if self.token:
            return

        # Check OAuth authentication
        if not self.oauth_tokens:
            raise AuthenticationError(
                "No authentication configured. Please provide one of:\n"
                "1. Long-lived access token in config file (ha_token)\n"
                "2. Run OAuth authentication: halinuxcompanion --oauth"
            )

        # Ensure token is valid (will raise if refresh fails)
        self.oauth_tokens = await ensure_valid_oauth_token(
            self.oauth_tokens, self.session, self.instance_url, self.storage
        )

    def has_valid_auth(self) -> bool:
        """Check if we have any valid authentication."""
        return bool(self.token) or bool(self.oauth_tokens)

    @property
    def instance_url(self) -> str:
        """Get the Home Assistant instance URL."""
        return self.companion.ha_url

    @property
    def webhook_url(self) -> str:
        """Get the full webhook URL."""
        if not self.registration:
            raise ValueError("Device not registered")
        return self.instance_url + self.registration.webhook_path

    async def webhook_post(self, data: dict) -> ClientResponse:
        """Send a POST request to the webhook endpoint with the given type and data
        Simple wrapper that handles and logs response status, should be wrapped to handle clinet errors.
        :param type: Whats being posted, ussed for logging
        :param data: The data to send in the body of the request
        """
        logger.debug("Sending webhook POST")

        async with self.session.post(self.webhook_url, json=data) as res:
            logger.debug(f"Received response {res.status} to request")
            if res.status == SC_INVALID_JSON:
                logger.error(f"Invalid JSON {self.webhook_url}")
            if res.status == SC_MOBILE_COMPONENT_NOT_LOADED:
                logger.error(
                    f"The mobile_app component has not been loaded {self.webhook_url}"
                )
            elif res.status == SC_INTEGRATION_DELETED:
                logger.error(
                    f"Integration was deleted, need to re-register {self.webhook_url}"
                )
            return res

    async def get(self, endpoint: str, data=None, json=None) -> ClientResponse:
        return await self.request("GET", endpoint, data, json)

    async def post(self, endpoint: str, data=None, json=None) -> ClientResponse:
        return await self.request("POST", endpoint, data, json)

    async def request(
        self, method: str, endpoint: str, data=None, json=None
    ) -> ClientResponse:
        """Send a request to the given Home Assisntat endpoint.

        :param method: The HTTP method to use (GET, POST, etc.)
        :param endpoint: The endpoint to send the request to (must have a leading /)
        :param data: Data to send in the body of the request (raw)
        :param json: Data to send in the body of the request (JSON)
        :return: The response from Home Assistant
        """
        # Ensure we have valid authentication before making the request
        await self._ensure_authenticated()

        async def _try():
            return await self.session.request(
                method,
                self.instance_url + endpoint,
                headers=self.headers,
                data=data,
                json=json,
            )

        resp = await _try()

        # Check for authentication errors and retry once if OAuth refresh might help
        if resp.status == SC_UNAUTHORIZED and self.oauth_tokens:
            # OAuth token might have just expired, try refreshing
            await self._ensure_authenticated()
            return await _try()

        return resp


class Server:
    """HTTP server that listens for notifications from Home Assistant."""

    app: web.Application
    host: str
    port: int

    def __init__(self, companion: Companion) -> None:
        self.app = web.Application()
        self.host = companion.computer_ip  # TODO: Rename to listen_address
        self.port = companion.computer_port  # TODO: Rename to listen_port

    async def start(self) -> None:
        logger.info(f"Starting http server on {self.host}:{self.port}")
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"Server started on {self.host}:{self.port}")
