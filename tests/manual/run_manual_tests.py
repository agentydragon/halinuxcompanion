#!/usr/bin/env python3
"""Runner script for Robot Framework manual tests."""

import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click
import docker
import requests
from docker.errors import APIError, NotFound


def ensure_ha_container_running() -> bool:
    """Ensure Home Assistant container is running using Docker SDK."""
    click.echo("\n🏠 Checking Home Assistant container...")

    try:
        client = docker.from_env()

        # First, clean up any existing container to ensure fresh state
        try:
            container = client.containers.get("homeassistant-test")
            click.echo("Removing existing container for fresh start...")
            container.stop(timeout=10)
            container.remove(force=True, v=True)  # v=True removes volumes
            time.sleep(2)  # Give docker time to clean up
        except NotFound:
            pass

        # Get path to ha_test_config.yaml
        config_file = Path(__file__).parent / "ha_test_config.yaml"

        # Start fresh container using Docker SDK
        click.echo("Starting fresh Home Assistant container...")
        container = client.containers.run(
            image="ghcr.io/home-assistant/home-assistant:stable",
            name="homeassistant-test",
            ports={"8123/tcp": 8123},
            volumes={
                str(config_file): {"bind": "/config/configuration.yaml", "mode": "ro"},
                "/etc/localtime": {"bind": "/etc/localtime", "mode": "ro"},
            },
            tmpfs={"/config/.storage": ""},
            environment={"TZ": "UTC"},
            detach=True,
            remove=True,
            healthcheck={"test": ["CMD", "curl", "-f", "http://localhost:8123/api/"]},
        )

        click.echo(f"✓ Home Assistant container started with ID: {container.short_id}")
        return True

    except APIError as e:
        click.echo(f"❌ Docker API error: {e}")
        return False
    except Exception as e:
        click.echo(f"❌ Error managing container: {e}")
        return False


def wait_for_ha_ready(ha_url: str, timeout: int = 120) -> bool:
    """Wait for Home Assistant to be ready."""
    click.echo(f"\n⏳ Waiting for Home Assistant at {ha_url} to be ready...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{ha_url}/api/", timeout=5)
            if response.status_code in (200, 401):  # 401 is expected without auth
                click.echo("✓ Home Assistant is responding")

                # Verify onboarding is NOT done (fresh container requirement)
                try:
                    response = requests.get(f"{ha_url}/api/onboarding", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, list):
                            # List response means onboarding steps are available
                            click.echo("✓ Fresh container ready for onboarding")
                            return True
                        if isinstance(data, dict) and data.get("done"):
                            click.echo("❌ Onboarding already done! Should never happen with fresh container.")
                            return False
                except Exception as e:
                    click.echo(f"⚠ Could not verify onboarding status: {e}")
                    # Continue anyway - onboarding setup will fail if something is wrong

                return True
        except requests.exceptions.RequestException:
            pass

        time.sleep(2)
        click.echo(".", nl=False)

    click.echo("\n❌ Timeout waiting for Home Assistant")
    return False


def setup_ha_user(ha_url: str) -> str | None:
    """Setup initial Home Assistant user and return access token."""
    click.echo("\n🔑 Setting up Home Assistant user...")

    try:
        # Complete onboarding
        response = requests.post(
            f"{ha_url}/api/onboarding/users",
            json={
                "username": "admin",
                "password": "admin123",
                "name": "Test Admin",
                "language": "en",
                "client_id": ha_url,
            },
            timeout=10,
        )

        if response.status_code != 200:
            click.echo(f"❌ Failed to complete onboarding: {response.status_code}")
            click.echo(f"Response: {response.text}")
            return None

        auth_code = response.json().get("auth_code")
        if not auth_code:
            click.echo("❌ No auth code received")
            return None

        click.echo("✓ Onboarding completed")

        # Exchange auth code for token
        response = requests.post(
            f"{ha_url}/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "client_id": ha_url,
            },
            timeout=10,
        )

        if response.status_code != 200:
            click.echo(f"❌ Failed to get token: {response.text}")
            return None

        access_token = response.json().get("access_token")
        if not access_token:
            click.echo("❌ No access token received")
            return None

        click.echo("✓ Access token obtained")
        return access_token

    except Exception as e:
        click.echo(f"❌ Error setting up user: {e}")
        return None


def cleanup_ha_container() -> None:
    """Stop and remove the Home Assistant container using Docker SDK."""
    click.echo("\n🧹 Cleaning up Home Assistant container...")

    try:
        client = docker.from_env()
        container = client.containers.get("homeassistant-test")
        try:
            container.stop(timeout=30)
            click.echo("✓ Home Assistant container stopped (and should be removed)")
        except Exception:
            # Force kill if graceful stop fails
            container.kill()
            click.echo("✓ Home Assistant container force killed (and should be removed)")
    except APIError as e:
        click.echo(f"⚠ Docker API error during cleanup: {e}")
    except Exception as e:
        click.echo(f"⚠ Error cleaning up container: {e}")


def check_virtualenv() -> bool:
    """Check if running in a virtual environment."""
    # Check for VIRTUAL_ENV environment variable
    if os.environ.get("VIRTUAL_ENV"):
        return True

    # Check if sys.prefix is different from sys.base_prefix
    # This is the standard way for Python 3.3+
    return sys.prefix != sys.base_prefix


@click.command()
@click.option(
    "--test",
    type=click.Choice(["bluetooth", "battery", "all"]),
    default="all",
    help="Which test suite to run",
)
@click.option(
    "--tag",
    multiple=True,
    help="Run only tests with specific tags",
)
@click.option(
    "--ha-token",
    envvar="HA_TOKEN",
    help="Home Assistant long-lived access token",
)
@click.option(
    "--ha-url",
    default="http://localhost:8123",
    help="Home Assistant URL",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path.cwd() / "manual_test_results",
    help="Directory for test results",
)
@click.option(
    "--no-ha-container",
    is_flag=True,
    help="Don't automatically manage Home Assistant container",
)
def main(
    test: str,
    tag: list[str],
    ha_token: str | None,
    ha_url: str,
    output_dir: Path,
    no_ha_container: bool,
):
    """Run manual tests for Home Assistant Linux Companion."""
    # Check if running in virtualenv
    if not check_virtualenv():
        click.echo(
            click.style(
                "\n⚠️  WARNING: Not running in a virtual environment!\n",
                fg="yellow",
                bold=True,
            )
        )
        click.echo("This can cause issues with pytest-socket and other system packages.")
        click.echo("Please activate a virtual environment first:\n")
        click.echo("  python -m venv venv")
        click.echo("  source venv/bin/activate")
        click.echo("  pip install -r requirements.txt\n")
        sys.exit(1)

    click.echo(
        click.style(
            "\n🚀 Home Assistant Linux Companion Manual Test Suite",
            fg="green",
            bold=True,
        )
    )

    # Global flag to track if cleanup has been done
    cleanup_done = False

    def ensure_cleanup():
        """Ensure cleanup happens only once."""
        nonlocal cleanup_done
        if not cleanup_done and not no_ha_container:
            cleanup_done = True
            cleanup_ha_container()

    def signal_handler(signum, frame):
        """Handle termination signals."""
        click.echo(f"\n\n⚠️  Received signal {signum}! Cleaning up...")
        ensure_cleanup()  # Show messages during signal handling
        # Re-raise the signal to let the OS handle it properly
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    # Manage HA container if needed
    if not no_ha_container:
        # Register cleanup handlers for all common signals
        for sig in [signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT]:
            signal.signal(sig, signal_handler)

        # Also register atexit handler as last resort
        atexit.register(lambda: ensure_cleanup())

        if not ensure_ha_container_running():
            click.echo(click.style("\n❌ Failed to start Home Assistant container", fg="red"))
            sys.exit(1)

        # Wait for HA to be ready
        if not wait_for_ha_ready(ha_url):
            click.echo(click.style("\n❌ Home Assistant failed to become ready", fg="red"))
            sys.exit(1)

        # Setup initial user if needed
        if not ha_token:
            ha_token = setup_ha_user(ha_url)
            if not ha_token:
                click.echo(click.style("\n❌ Failed to setup Home Assistant user", fg="red"))
                sys.exit(1)
            click.echo(f"\n✅ Home Assistant token obtained: {ha_token[:20]}...")

    # Build robot command
    cmd = ["robot"]

    # Add output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd.extend(["--outputdir", str(output_dir)])

    # Add tags if specified
    if tag:
        for t in tag:
            cmd.extend(["--include", t])

    # Add variables
    cmd.extend(["--variable", f"HA_URL:{ha_url}"])
    if ha_token:
        cmd.extend(["--variable", f"HA_TOKEN:{ha_token}"])

    # Add test files
    if test == "bluetooth":
        cmd.append("bluetooth_scenarios.robot")
    elif test == "battery":
        cmd.append("battery_scenarios.robot")
    else:
        cmd.extend(["bluetooth_scenarios.robot", "battery_scenarios.robot"])

    # Show command
    click.echo(f"\nRunning: {' '.join(cmd)}\n")

    # Execute tests
    returncode = 1
    proc = None

    # Change to test directory
    os.chdir(Path(__file__).parent)

    try:
        # Use subprocess.call for proper TTY handling and signal propagation
        # This is better than Popen for interactive commands
        returncode = subprocess.call(cmd)

        if returncode == 0:
            click.echo(click.style("\n✅ Tests completed successfully!", fg="green"))
        elif returncode == 130:
            click.echo("\n⚠️  Tests interrupted by user")
        else:
            click.echo(click.style(f"\n❌ Tests failed with return code: {returncode}", fg="red"))

        # Show report location
        report_file = output_dir / "report.html"
        if report_file.exists():
            click.echo(f"\n📊 Test report: {report_file}")
            click.echo(f"📋 Log file: {output_dir / 'log.html'}")

    except KeyboardInterrupt:
        # This shouldn't normally happen with subprocess.call, but just in case
        click.echo("\n\n⚠️  Interrupted!")
        returncode = 130
    except Exception as e:
        click.echo(click.style(f"\n❌ Error running tests: {e}", fg="red"))
        returncode = 1
    finally:
        # Ensure cleanup always happens
        ensure_cleanup()

    sys.exit(returncode)


if __name__ == "__main__":
    main()
