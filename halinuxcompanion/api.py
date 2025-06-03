import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aiohttp import ClientResponse, ClientSession, web
from jinja2 import Environment, PackageLoader, select_autoescape

from .models import RegistrationData
from .oauth import AuthenticationError, OAuthFlow

if TYPE_CHECKING:
    from .secret_storage import SecretStorage

from .constants import SC_INTEGRATION_DELETED, SC_INVALID_JSON, SC_MOBILE_COMPONENT_NOT_LOADED, SC_UNAUTHORIZED

logger = logging.getLogger(__name__)


@dataclass
class API:
    """Class that handles Home Assisntat HTTP API calls"""

    instance_url: str
    session: ClientSession
    storage: "SecretStorage"
    oauth_client_id: str
    oauth_redirect_uri: str
    registration: RegistrationData | None = None

    # def __init__(
    #    self,
    #    instance_url: str,
    #    storage: "SecretStorage",
    #    session: ClientSession,
    # ) -> None:
    #    """Initialize API client.

    #    Args:
    #        instance_url: Home Assistant URL
    #        storage: Secret storage backend for authentication
    #        session: aiohttp session to use for requests
    #    """
    #    self.session = session
    #    self.instance_url = instance_url.rstrip("/")
    #    self.storage = storage

    def _oauth_flow(self) -> OAuthFlow:
        return OAuthFlow(
            self.instance_url,
            client_id=self.oauth_client_id,
            redirect_uri=self.oauth_redirect_uri,
        )

    async def _ensure_valid_token(self) -> str:
        """Ensure we have valid authentication, refreshing OAuth token if needed.

        Raises:
            AuthenticationError: If authentication fails
        """

        # Check OAuth authentication
        if self.storage.oauth_tokens:
            # Ensure OAutht oken is valid (will raise if refresh fails)
            # If token is still valid, return as-is
            if self.storage.oauth_tokens.expires_soon:
                logger.info("Access token expired, refreshing...")
                try:
                    self.storage.oauth_tokens = await self._oauth_flow().refresh_access_token(
                        self.session, self.storage.oauth_tokens.refresh_token
                    )
                except AuthenticationError:
                    raise AuthenticationError(
                        "OAuth refresh failed. Please re-authenticate:\n    halinuxcompanion oauth"
                    )
            logger.info("OAuth token refreshed successfully")
            return self.storage.oauth_tokens.access_token
        if token := self.storage.long_lived_token:
            # If we have a long-lived token, we're good
            return token
        raise AuthenticationError(
            "No authentication available. Please provide one of:\n"
            "1. Long-lived access token in config file (ha_token)\n"
            "2. Run OAuth authentication: halinuxcompanion --oauth"
        )

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
        logger.debug(f"Sending webhook POST: {data}")

        async with self.session.post(self.webhook_url, json=data) as res:
            logger.debug(f"Received response {res.status} to request")
            if res.status == SC_INVALID_JSON:
                logger.error(f"Invalid JSON {self.webhook_url}")
            if res.status == SC_MOBILE_COMPONENT_NOT_LOADED:
                logger.error(f"The mobile_app component has not been loaded {self.webhook_url}")
            elif res.status == SC_INTEGRATION_DELETED:
                logger.error(f"Integration was deleted, need to re-register {self.webhook_url}")
            return res

    async def get(self, endpoint: str, data=None, json=None) -> ClientResponse:
        return await self.request("GET", endpoint, data, json)

    async def post(self, endpoint: str, data=None, json=None) -> ClientResponse:
        return await self.request("POST", endpoint, data, json)

    async def request(self, method: str, endpoint: str, data=None, json=None) -> ClientResponse:
        """Send a request to the given Home Assistant endpoint.

        :param method: HTTP method to use (GET, POST, etc.)
        :param endpoint: Endpoint to send the request to (must have a leading /)
        :param data: Data to send in the body of the request (raw)
        :param json: Data to send in the body of the request (JSON)
        :return: The response from Home Assistant
        """

        # Ensure we have valid authentication before making the request
        async def _try():
            token = await self._ensure_valid_token()
            return await self.session.request(
                method,
                self.instance_url + endpoint,
                headers={"Authorization": f"Bearer {token}"},
                data=data,
                json=json,
            )

        resp = await _try()

        # Check for authentication errors and retry once if OAuth refresh might help
        # (OAuth token might have just expired)
        if resp.status == SC_UNAUTHORIZED and self.storage.oauth_tokens:
            resp = await _try()
        return resp  # type: ignore[no-any-return]


@dataclass
class OAuthSession:
    """Active OAuth session state."""

    state: str
    result_future: asyncio.Future[dict[str, Any]] = field(default_factory=asyncio.Future)


class Server:
    """Unified HTTP server for OAuth callbacks and Home Assistant notifications."""

    app: web.Application
    host: str
    port: int
    runner: web.AppRunner
    _oauth_session: OAuthSession | None = None
    _notification_handler: Callable[[web.Request], Awaitable[web.Response]] | None = None
    _sensor_state_provider: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None
    _jinja_env: Environment

    def __init__(self, host: str, port: int, expose_sensor_state: bool = False) -> None:
        """Initialize server with explicit host and port.

        Args:
            host: IP address or hostname to bind to
            port: Port number to listen on (must be >= 1)
            expose_sensor_state: Whether to expose sensor state on root path
        """
        if port < 1:
            raise ValueError(f"Port must be >= 1, got {port}")

        # Set max request size to 1MB to prevent DoS attacks
        self.app = web.Application(client_max_size=1024 * 1024)  # 1MB
        self.host = host
        self.port = port
        self.runner = web.AppRunner(self.app)
        self._site: web.TCPSite | None = None

        # Initialize Jinja2 environment
        self._jinja_env = Environment(
            loader=PackageLoader("halinuxcompanion", "resources"),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.app.router.add_get("/auth/callback", self._handle_oauth_callback)
        self.app.router.add_post("/notify", self._handle_notification)

        # Only expose sensor state if explicitly enabled
        if expose_sensor_state:
            self.app.router.add_get("/", self._handle_root)

    async def __aenter__(self) -> "Server":
        """Enter the async context manager and start the server."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager and stop the server."""
        await self.stop()

    async def _handle_oauth_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback requests."""
        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")

        # No active OAuth session
        if self._oauth_session is None:
            return web.Response(
                text=(
                    "<h1>No OAuth Flow Active</h1>"
                    "<p>This callback was received but no OAuth flow is currently active.</p>"
                    "<p>This might happen if:</p>"
                    "<ul>"
                    "<li>The OAuth flow timed out</li>"
                    "<li>You refreshed this page after authentication</li>"
                    "<li>Multiple OAuth attempts were made</li>"
                    "</ul>"
                ),
                content_type="text/html",
                status=400,
            )

        # State mismatch - security check
        if state != self._oauth_session.state:
            error_msg = f"State mismatch: expected {self._oauth_session.state}, got {state}"
            self._oauth_session.result_future.set_exception(AuthenticationError(error_msg))

            return web.Response(
                text=(
                    "<h1>Invalid OAuth State</h1>"
                    f"<p>{error_msg}</p>"
                    "<p>This might be an old authentication attempt or a security issue.</p>"
                ),
                content_type="text/html",
                status=400,
            )

        # Handle OAuth error from HA
        if error:
            error_desc = request.query.get("error_description", error)
            self._oauth_session.result_future.set_exception(AuthenticationError(f"OAuth error: {error_desc}"))
            return web.Response(
                text=(f"<h1>Authentication Failed</h1><p>Home Assistant returned an error: {error_desc}</p>"),
                content_type="text/html",
                status=400,
            )

        # Handle success
        if code:
            # Pass the code to the waiting OAuth flow
            self._oauth_session.result_future.set_result({"code": code, "state": state})

            return web.Response(
                text=(
                    "<h1>Authentication Successful!</h1>"
                    "<p>You have been authenticated with Home Assistant.</p>"
                    "<p>You can now close this window and return to the terminal.</p>"
                ),
                content_type="text/html",
            )

        # No code and no error
        self._oauth_session.result_future.set_exception(AuthenticationError("No authorization code received"))
        return web.Response(
            text=("<h1>No Authorization Code</h1><p>Home Assistant did not provide an authorization code.</p>"),
            content_type="text/html",
            status=400,
        )

    async def run_oauth_flow(self, state: str) -> dict[str, Any]:
        """Run OAuth flow and wait for callback.

        Args:
            state: OAuth state for security

        Returns:
            Dict with 'code' and 'state' from the callback

        Raises:
            RuntimeError: If OAuth flow is already active
            AuthenticationError: If authentication fails
        """
        if self._oauth_session is not None:
            raise RuntimeError("OAuth flow already in progress")

        # Create OAuth session
        self._oauth_session = OAuthSession(state=state)

        try:
            # Wait for callback
            result = await self._oauth_session.result_future
            return result
        finally:
            # Clean up session
            self._oauth_session = None

    async def _handle_notification(self, request: web.Request) -> web.Response:
        """Handle notification requests from Home Assistant."""
        if self._notification_handler is None:
            return web.Response(text="Notification handler not configured", status=503)
        return await self._notification_handler(request)

    def set_notification_handler(self, handler: Callable[[web.Request], Awaitable[web.Response]]) -> None:
        """Set the notification handler."""
        self._notification_handler = handler

    def set_sensor_state_provider(self, provider: Callable[[], Awaitable[list[dict[str, Any]]]]) -> None:
        """Set the sensor state provider callback."""
        self._sensor_state_provider = provider

    async def start(self) -> None:
        logger.info(f"Starting http server on {self.host}:{self.port}")
        await self.runner.setup()
        self._site = web.TCPSite(self.runner, self.host, self.port)
        await self._site.start()
        logger.info(f"Server started on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the HTTP server."""
        await self.runner.cleanup()

    async def _handle_root(self, _request: web.Request) -> web.Response:
        """Handle root path - display sensor states using Jinja2 template."""
        template = self._jinja_env.get_template("status_page.html.j2")

        context: dict[str, Any] = {
            "sensor_states": None,
            "error": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if self._sensor_state_provider is None:
            context["error"] = "Sensor state provider not configured. The application may still be starting up."
        else:
            try:
                context["sensor_states"] = await self._sensor_state_provider()
            except Exception as e:
                logger.exception("Error getting sensor states")
                context["error"] = f"Error retrieving sensor states: {e}"

        html = template.render(**context)
        return web.Response(text=html, content_type="text/html")

    @property
    def base(self) -> str:
        """Get the base URL for the server."""
        return f"http://{self.host}:{self.port}"

    @property
    def notify_endpoint(self) -> str:
        """Get the notification endpoint URL."""
        return f"{self.base}/notify"
