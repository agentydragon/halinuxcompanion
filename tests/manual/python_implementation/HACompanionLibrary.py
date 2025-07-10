"""Robot Framework library for Home Assistant Linux Companion testing."""

import json
import os
import shlex
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CalledProcessError
from typing import IO, Any, cast

import docker
import requests
from jinja2 import Environment, FileSystemLoader
from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_fixed


def format_ha_timestamp(dt: datetime) -> str:
    """Format a datetime object for Home Assistant API."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


@dataclass
class HAConnection:
    """Home Assistant connection context."""

    url: str
    token: str

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> Any:
        """Make a request to the HA API."""
        response = requests.request(
            method,
            f"{self.url}/api{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            params=params,
            json=json,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def ping(self) -> None:
        self.get("/")

    def is_alive(self) -> bool:
        """Check if HA is responsive with valid authentication."""
        try:
            self.ping()
            return True
        except requests.exceptions.ConnectionError as e:
            logger.debug(f"Connection error checking HA: {e}")
            return False
        except requests.exceptions.HTTPError as e:
            logger.debug(f"HTTP error checking HA: {e}")
            return False

    @retry(
        retry=retry_if_exception_type(requests.exceptions.ConnectionError),
        stop=stop_after_delay(60),
        wait=wait_fixed(2),
    )
    def wait_until_ready(self) -> None:
        """Wait for Home Assistant to be ready with valid authentication."""
        self.ping()

    def get_states(self) -> list[dict]:
        """Get all current states."""
        return cast("list[dict]", self.get("/states"))

    def get_history(self, start_time: datetime, end_time: datetime) -> list[list[dict]]:
        """Get history for all entities."""
        return cast(
            "list[list[dict]]",
            self.get(
                f"/history/period/{format_ha_timestamp(start_time)}",
                params={
                    "minimal_response": "false",
                    "no_attributes": "false",
                    "end_time": format_ha_timestamp(end_time),
                },
            ),
        )

    def get_devices(self) -> list[dict]:
        """Get device registry."""
        return cast("list[dict]", self.get("/config/device_registry/list"))

    def get_entities(self) -> list[dict]:
        """Get entity registry."""
        return cast("list[dict]", self.get("/config/entity_registry/list"))


class HACompanionLibrary:
    """Library for testing Home Assistant Linux Companion."""

    ROBOT_LIBRARY_SCOPE = "SUITE"

    def __init__(self):
        self.ha_url = "http://localhost:8123"
        self.ha_token = None
        self.builtin = BuiltIn()
        self.test_start_time = None
        self.open_log_files: list[IO] = []

    @contextmanager
    def home_assistant_docker(self):
        """Context manager for running Home Assistant in Docker."""
        docker_client = docker.from_env()
        # Remove any existing container with same name
        try:
            existing = docker_client.containers.get("ha_test")
            logger.info(f"Found existing ha_test container in {existing.status} state, removing...")
            existing.stop()
            existing.remove()
        except docker.errors.NotFound:
            pass  # Good, no existing container
        # Create container
        logger.info("Starting Home Assistant container...")
        container = docker_client.containers.run(
            "homeassistant/home-assistant:stable",
            name="ha_test",
            detach=True,
            ports={"8123/tcp": 8123},
            volumes={
                str(Path(__file__).parent / "ha_test_config.yaml"): {
                    "bind": "/config/configuration.yaml",
                    "mode": "ro",
                },
                "/etc/localtime": {"bind": "/etc/localtime", "mode": "ro"},
            },
            environment={"TZ": "UTC"},
            remove=False,
        )
        logger.info(f"Home Assistant container {container.short_id} started, waiting to initialize (up to 120 s)...")
        try:
            # Show container logs while waiting
            ha_ready = threading.Event()
            stop_logs = threading.Event()

            def stream_logs():
                for line in container.logs(stream=True, follow=True):
                    if stop_logs.is_set():
                        break
                    log_line = line.decode("utf-8").strip()
                    logger.info(f"HA: {log_line}")

                    # Check if HA is ready
                    if "Home Assistant initialized" in log_line:
                        ha_ready.set()
                        return

            log_thread = threading.Thread(target=stream_logs)
            log_thread.start()

            try:
                # Wait for either HA to be ready or timeout
                print("Waiting for Home Assistant to be ready...")
                ha_ready.wait(timeout=120)  # Wait up to 2 minutes
            finally:
                stop_logs.set()
            if not ha_ready.is_set():
                raise RuntimeError("Home Assistant did not start within 120 seconds")

            logger.info("Setting up Home Assistant user...")
            self.ha_token = self._obtain_ha_token()

            # Now that we have a token (or confirmed trusted networks), verify connection
            conn = HAConnection(url=self.ha_url, token=self.ha_token)
            logger.info(f"✓ Home Assistant is ready! URL: {self.ha_url}")
            conn.ping()
            yield conn
        finally:
            logger.info("Stopping Home Assistant container...")
            try:
                container.stop()
                container.remove()
            except Exception as e:
                logger.warn(f"Error stopping container: {e}")

    # TODO: never called, call
    def collect_dbus_diagnostics(self, output_dir: str, prefix: str) -> None:
        """Collect DBus diagnostics."""
        base = Path(output_dir) / prefix
        diag_file = base / "dbus_diagnostics.json"
        with open(diag_file, "w") as f:
            diag: dict[str, Any] = {"timestamp": datetime.now().isoformat()}

            def _run(cmd: list[str]) -> dict[str, Any]:
                """Run a command and return output."""
                out = {"command": shlex.join(cmd)}
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
                except subprocess.TimeoutExpired:
                    return out | {"error": "Command timed out"}
                except Exception as e:
                    return out | {"error": str(e)}
                else:
                    return out | {
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }

            diag.update(
                {
                    " ".join(command): _run(command)
                    for command in (
                        ["busctl", "tree", "org.bluez"],
                        ["busctl", "introspect", "org.bluez", "/org/bluez"],
                        ["systemctl", "status", "bluetooth"],
                        ["rfkill", "list"],
                        ["bluetoothctl", "show"],
                        ["bluetoothctl", "devices"],
                    )
                }
            )
            json.dump(diag, f, indent=2)

        logger.info(f"DBus diagnostics saved to {diag_file}")

    @contextmanager
    def halinuxcompanion_process(self, output_dir: str):
        """Context manager for running halinuxcompanion with logging."""
        log_file = Path(output_dir) / "halinuxcompanion.log"
        process = None
        logger.info("Starting halinuxcompanion with debug logging...")
        with open(log_file, "w") as log_handle:
            try:
                process = subprocess.Popen(
                    ["halinuxcompanion", "run", "--debug"],
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=os.environ.copy()
                    | {
                        "DBUS_VERBOSE": "1",
                        "PYTHONUNBUFFERED": "1",
                    },
                )
                if process.poll() is not None:
                    raise RuntimeError("halinuxcompanion failed to start")
                logger.info(f"Started halinuxcompanion (PID {process.pid}), logs: {log_file}")
                yield process

            finally:
                # Clean shutdown
                if process and process.poll() is None:
                    logger.info("Stopping halinuxcompanion...")
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                        logger.info("halinuxcompanion stopped gracefully")
                    except subprocess.TimeoutExpired:
                        logger.warn("halinuxcompanion did not stop gracefully, forcing...")
                        process.kill()
                        process.wait()
                    except Exception as e:
                        logger.error(f"Error stopping halinuxcompanion: {e}")

    def mark_test_start(self) -> None:
        """Mark the start time of the test for history collection."""
        self.test_start_time = datetime.now(timezone.utc)
        logger.info(f"Test start time marked: {self.test_start_time.isoformat()}")

    def collect_ha_sensor_data(self, output_dir: str, prefix: str) -> None:
        """Collect all sensor states and history from Home Assistant."""
        assert self.ha_token, "HA token is required for data collection"
        assert self.test_start_time, "Test start time must be marked before data collection"

        collection_time = datetime.now(timezone.utc)

        data = {
            "collection_time": collection_time.isoformat(),
            "test_start_time": self.test_start_time.isoformat(),
            "history": {},
        }

        ha = HAConnection(url=self.ha_url, token=self.ha_token)
        try:
            # Collect all data - this is our test instance.
            # Get all current states.
            data["states"] = {state["entity_id"]: state for state in ha.get_states()}
            logger.info(f"- {len(data['states'])} states")

            history_data = ha.get_history(self.test_start_time, collection_time)
            for entity_history in history_data:
                if entity_history:
                    entity_id = entity_history[0].get("entity_id")
                    data["history"][entity_id] = entity_history
            logger.info(f"- {len(data['history'])} entities with history")

            data["devices"] = {device["id"]: device for device in ha.get_devices()}
            logger.info(f"- {len(data['devices'])} devices")

            data["entities"] = {entity["entity_id"]: entity for entity in ha.get_entities()}
            logger.info(f"- {len(data['entities'])} entities")
        except Exception as e:
            logger.error(f"Error collecting HA data: {e}")
            data["error"] = str(e)

        # Save collected data
        base = Path(output_dir) / prefix
        data_file = base / "ha_sensor_data.json"
        data_file.write_text(json.dumps(data, indent=2))
        logger.info(f"Home Assistant sensor data saved to {data_file}")

        # Generate a human-readable summary using Jinja2
        env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))
        (base / "ha_sensor_summary.txt").write_text(env.get_template("ha_sensor_summary.txt.j2").render(**data))

    def take_system_screenshot(self, output_dir: str, name: str) -> None:
        """Take a screenshot of the desktop."""
        output_path = Path(output_dir) / f"{name}.png"

        # Try different screenshot tools
        for tool_cmd in [
            ["gnome-screenshot", "-f", str(output_path)],
            ["scrot", str(output_path)],
            ["import", "-window", "root", str(output_path)],
        ]:
            try:
                subprocess.run(tool_cmd, capture_output=True, check=True)
                logger.info(f"Screenshot saved to {output_path}")
                return
            except (FileNotFoundError, CalledProcessError):
                continue

        logger.warn("No screenshot tool available")

    def _obtain_ha_token(self, username: str = "admin", password: str = "admin123") -> str:
        """Set up initial HA user and return access token."""
        logger.info("Completing Home Assistant onboarding...")
        response = requests.post(
            f"{self.ha_url}/api/onboarding/users",
            json={
                "username": username,
                "password": password,
                "name": "Test Admin",
                "language": "en",
                "client_id": "http://localhost:8123/",  # (???)
            },
        )
        auth_code = response.json()["auth_code"]
        logger.info("✓ Onboarding completed successfully")

        # Step 3: Exchange auth code for tokens
        response = requests.post(
            f"{self.ha_url}/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "client_id": "http://localhost:8123/",
            },
        )
        response.raise_for_status()
        access_token = response.json()["access_token"]
        assert access_token, "No access token received"
        logger.info("✓ Successfully obtained access token")

        return cast("str", access_token)
