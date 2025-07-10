"""Diagnostic data collector for manual testing."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path  # noqa: TC003
from typing import IO

logger = logging.getLogger(__name__)


class ProcessLogger:
    """Context manager for a subprocess with logging."""

    def __init__(self, cmd: list[str], log_file: Path):
        self.cmd = cmd
        self.log_file = log_file
        self.log_handle: IO | None = None
        self.proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> asyncio.subprocess.Process:
        """Start the process and open log file."""
        self.log_handle = open(self.log_file, "wb")  # noqa: SIM115
        self.proc = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=self.log_handle,
            stderr=asyncio.subprocess.STDOUT,
        )
        return self.proc

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop the process and close log file."""
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
            except Exception:
                logger.exception("Error terminating process")

        if self.log_handle:
            try:
                self.log_handle.close()
            except Exception:
                logger.exception("Error closing log file")


class DiagnosticCollection:
    """Context manager for diagnostic collection during a scenario."""

    def __init__(self, collector: DiagnosticCollector, scenario_name: str):
        self.collector = collector
        self.scenario_name = scenario_name
        self.start_time: datetime | None = None
        self.collectors: list[asyncio.Task] = []

    async def __aenter__(self) -> DiagnosticCollection:
        """Start diagnostic collection."""
        self.start_time = datetime.now()

        async def _run(cmd: list[str], filename: str) -> None:
            async with ProcessLogger(cmd, self.scenario_dir / filename) as proc:
                await proc.wait()

        # Start all collectors as background tasks
        self.collectors = [
            asyncio.create_task(_run(cmd, log_filename))
            for cmd, log_filename in [
                (["dbus-monitor", "--system"], "dbus_monitor.log"),
                (["dbus-monitor", "--system", "--pcap"], "dbus_monitor.pcap"),
                (
                    ["journalctl", "-u", "bluetooth", "-f", "--since", "now"],
                    "journalctl_bluetooth.log",
                ),
            ]
        ]
        return self

    @property
    def scenario_dir(self) -> Path:
        """Return the directory for the current scenario."""
        return self.collector.results_dir / self.scenario_name

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop diagnostic collection and save summary."""
        # Cancel all collector tasks. Wait to complete.
        for task in self.collectors:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.collectors, return_exceptions=True)

        assert self.start_time is not None
        end_time = datetime.now()
        (self.scenario_dir / "collection_summary.json").write_text(
            json.dumps(
                {
                    "scenario": self.scenario_name,
                    "start_time": self.start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration": ((end_time - self.start_time).total_seconds(),),
                    "files_collected": [
                        {
                            "name": file.name,
                            "size": file.stat().st_size,
                            "type": file.suffix,
                        }
                        for file in self.scenario_dir.iterdir()
                        if file.is_file()
                    ],
                },
                indent=2,
            )
        )


class DiagnosticCollector:
    """Manages diagnostic collection for test scenarios."""

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir

    @asynccontextmanager
    async def collect_for_scenario(self, scenario_name: str):
        """Context manager for collecting diagnostics during a scenario."""
        collection = DiagnosticCollection(self, scenario_name)
        async with collection:
            yield collection

    def collect_system_info(self) -> dict[str, str]:
        return {
            key: subprocess.check_output(cmd, text=True).strip()
            for key, cmd in {
                "os": ["lsb_release", "-a"],
                "python": ["python3", "--version"],
                "bluetoothctl": ["bluetoothctl", "--version"],
                "kernel": ["uname", "-a"],
                "systemd": ["systemctl", "--version"],
            }.items()
        }
