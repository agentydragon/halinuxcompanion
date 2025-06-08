#!/usr/bin/env python3
"""Interactive manual test runner for Home Assistant Linux Companion.

This script guides testers through manual test scenarios, collecting diagnostics
and verification results at each step.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

import click
from diagnostic_collector import DiagnosticCollector
from jinja2 import Environment, FileSystemLoader
from test_environment import TestEnvironment
from test_scenarios import bluetooth_scenarios

# Configure logging to show progress
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)


class VerificationStatus(str, Enum):
    """Status of a manual verification step."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_VERIFIED = "not_verified"


class TestRunner:
    """Orchestrates manual test execution."""

    def __init__(self, test_dir: Path):
        self.test_dir = test_dir
        self.test_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.env = TestEnvironment(self.results_dir)
        self.collector = DiagnosticCollector(self.results_dir)
        self.results: dict[str, Any] = {
            "test_id": self.test_id,
            "start_time": datetime.now().isoformat(),
        }

    @property
    def results_dir(self) -> Path:
        return self.test_dir / f"results_{self.test_id}"

    def print_header(self, text: str) -> None:
        """Print a formatted header."""
        click.echo("\n" + "=" * 80)
        click.echo(f" {text}")
        click.echo("=" * 80 + "\n")

    def print_step(self, step_num: int, total: int, instruction: str) -> None:
        """Print a test step instruction."""
        click.echo(f"\n[Step {step_num}/{total}] {instruction}")
        click.echo("-" * 40)

    def get_verification(self, prompt: str, required: bool = True) -> dict[str, Any]:
        """Get verification from tester with optional notes."""
        click.echo(f"\n✓ {prompt}")

        # Response to status mapping

        response_mapping = {
            "Y": VerificationStatus.PASSED,
            "N": VerificationStatus.FAILED,
            "S": VerificationStatus.SKIPPED,
        }

        while True:
            # Click Choice validates input automatically and converts to uppercase
            response = click.prompt(
                "Did you verify this? [Y]es / [N]o / [S]kip",
                type=click.Choice(list(response_mapping.keys()), case_sensitive=False),
            ).upper()

            status = response_mapping[response]

            # Check if skip is allowed for required steps
            if status == VerificationStatus.SKIPPED and required:
                click.echo(click.style("⚠️  This verification is required!", fg="yellow"))
                if not click.confirm("Skip anyway?", default=False):
                    continue

            result = {
                "verified": status,
                "timestamp": datetime.now().isoformat(),
            }

            # Ask for notes (for all statuses)
            if click.confirm("Add notes?", default=False):
                # TODO: don't truncate previous notes if previoslyu set
                result["notes"] = self.get_notes()

            # Warn about failed required steps
            if status == VerificationStatus.FAILED and required:
                click.echo(click.style("⚠️  This verification failed but is required!", fg="yellow"))
                if not click.confirm("Continue anyway?", default=False):
                    continue  # Ask again

            return result

    def get_notes(self) -> str:
        """Get notes from user, optionally using $EDITOR."""
        if not click.confirm("Use editor?", default=False):
            return cast("str", click.prompt("Notes", default="", type=str))
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=True) as f:
            f.write("# Test Notes\n\n")
            f.flush()
            subprocess.check_call([os.environ.get("EDITOR", "nano"), f.name])
            return Path(f.name).read_text()

    async def run_scenario(self, scenario_name: str, scenario_func) -> dict[str, Any]:
        """Run a single test scenario."""
        self.print_header(f"Test Scenario: {scenario_name}")

        results: dict[str, Any] = {
            "name": scenario_name,
            "start_time": datetime.now().isoformat(),
        }

        try:
            # Run the scenario. Collect diagnostics during the scenario.
            async with self.collector.collect_for_scenario(scenario_name):
                steps = await scenario_func(self)
        except Exception as e:
            results["error"] = str(e)
            results["passed"] = False
            click.echo(click.style(f"\n❌ Scenario failed: {e}", fg="red"))
        else:
            results["steps"] = steps
            # A scenario passes if all steps are either PASSED or SKIPPED
            # It fails if any step is FAILED or NOT_VERIFIED
            results["passed"] = all(
                step.get("verified") in [VerificationStatus.PASSED, VerificationStatus.SKIPPED] for step in steps
            )
        finally:
            results["end_time"] = datetime.now().isoformat()

        return results

    async def run_all_tests(self) -> None:
        """Run all test scenarios."""
        click.echo(
            click.style(
                "\n🚀 Home Assistant Linux Companion Manual Test Suite",
                fg="green",
                bold=True,
            )
        )
        click.echo(f"Test ID: {self.test_id}")
        click.echo(f"Results directory: {self.results_dir}")

        # Setup test environment
        click.echo("\n→ Starting Home Assistant Docker container...")

        await self.env.setup()
        click.echo("✓ Home Assistant running. Username: admin  Password: admin123")
        # Select scenarios to run
        all_scenarios = {
            "Bluetooth: Off → On": bluetooth_scenarios.test_bluetooth_off_to_on,
        }

        selected_scenarios = []
        click.echo("\nSelect scenarios to run:")
        for name, func in all_scenarios.items():
            if click.confirm(f"  Run '{name}'?", default=True):
                selected_scenarios.append((name, func))

        self.results["system"] = self.collector.collect_system_info()
        self.results["scenarios"] = {name: await self.run_scenario(name, func) for name, func in selected_scenarios}

        # Generate final report
        self.results["end_time"] = datetime.now().isoformat()
        self.generate_report()

        # Cleanup
        if click.confirm("\nCleanup test environment?", default=True):
            await self.env.cleanup()

    def generate_report(self) -> None:
        """Generate test report."""
        # Save raw JSON data
        report_json_path = self.results_dir / "test_report.json"
        report_json_path.write_text(json.dumps(self.results, indent=2))

        # Calculate stats
        scenarios = self.results["scenarios"]
        passed_count = sum(bool(r.get("passed")) for r in scenarios.values())
        failed_count = len(scenarios) - passed_count

        # Calculate duration
        start_dt = datetime.fromisoformat(self.results["start_time"])
        end_dt = datetime.fromisoformat(self.results["end_time"])

        # Collect files in results directory
        collected_files = []
        for file in sorted(self.results_dir.iterdir()):
            size = file.stat().st_size
            collected_files.append(
                {
                    "path": str(file.relative_to(self.results_dir)),
                    "size": (
                        f"{size:,} bytes" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
                        # TODO: use some kind of reasonable library
                    ),
                }
            )

        # Render template
        template_dir = Path(__file__).parent / "templates"
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template("test_report.md.j2")

        report_path = self.results_dir / "test_report.md"
        report_path.write_text(
            template.render(
                test_id=self.test_id,
                duration=str(end_dt - start_dt),
                passed_count=passed_count,
                failed_count=failed_count,
                results_dir=self.results_dir.name,
                collected_files=collected_files,
                **self.results,
            )
        )

        click.echo(f"\n📊 Test report generated: {report_path}")
        click.echo(f"📋 Raw data saved: {report_json_path}")


@click.command()
@click.option(
    "--test-dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=Path.cwd() / "manual_test_results",
    help="Directory for test results",
)
def main(test_dir: Path):
    """Run manual test suite for Home Assistant Linux Companion."""
    runner = TestRunner(test_dir)
    asyncio.run(runner.run_all_tests())


if __name__ == "__main__":
    main()
