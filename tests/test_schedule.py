from __future__ import annotations

import unittest
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cli.commands.schedule import (
    ResourceSnapshot,
    compute_next_run,
    schedule_cmd,
    seconds_until,
)


class ScheduleTests(unittest.TestCase):
    def test_compute_next_run_and_seconds_until(self) -> None:
        started_at = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
        next_run = compute_next_run(started_at, 12.0)
        self.assertEqual(next_run, datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc))

        seconds = seconds_until(next_run, now=started_at)
        self.assertEqual(seconds, 43_200.0)

    def test_schedule_skips_when_system_is_under_pressure(self) -> None:
        snapshot = ResourceSnapshot(
            load_1m=32.0,
            cpu_count=1,
            memory_available_mb=256.0,
            memory_total_mb=16_000.0,
            disk_free_gb=2.0,
            disk_total_gb=512.0,
        )

        with (
            patch("src.cli.commands.schedule.sample_resource_snapshot", return_value=snapshot),
            patch("src.cli.commands.schedule.run_evoskill_once") as run_once,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_start",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as start_write,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_run_start",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as run_start_write,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_run_result",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as run_result_write,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_stop",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as stop_write,
            patch("src.cli.commands.schedule.time.sleep", side_effect=KeyboardInterrupt),
        ):
            schedule_cmd.callback(
                interval_hours=12.0,
                min_free_memory_mb=2_048.0,
                max_load_per_cpu=1.5,
                min_disk_free_gb=5.0,
                verbose=False,
                quiet=False,
            )

        start_write.assert_called_once()
        run_start_write.assert_called_once()
        run_result_write.assert_called_once()
        run_once.assert_not_called()
        stop_write.assert_called_once()

    def test_schedule_runs_continue_mode_when_resources_are_healthy(self) -> None:
        snapshot = ResourceSnapshot(
            load_1m=0.5,
            cpu_count=8,
            memory_available_mb=8_192.0,
            memory_total_mb=16_000.0,
            disk_free_gb=128.0,
            disk_total_gb=512.0,
        )

        with (
            patch("src.cli.commands.schedule.sample_resource_snapshot", return_value=snapshot),
            patch("src.cli.commands.schedule.seconds_until", return_value=43_200.0),
            patch(
                "src.cli.commands.schedule.run_evoskill_once",
                return_value=SimpleNamespace(
                    run_id="run-123",
                    project_root=Path("/tmp/project"),
                    baseline_score=0.4,
                    final_score=0.6,
                    total_cost_usd=1.23,
                ),
            ) as run_once,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_start",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as start_write,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_run_start",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as run_start_write,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_run_result",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as run_result_write,
            patch(
                "src.cli.commands.schedule.record_watchdog_supervisor_stop",
                return_value=SimpleNamespace(status="ok", detail=None),
            ) as stop_write,
            patch("src.cli.commands.schedule.time.sleep", side_effect=KeyboardInterrupt) as sleep_mock,
        ):
            schedule_cmd.callback(
                interval_hours=12.0,
                min_free_memory_mb=2_048.0,
                max_load_per_cpu=1.5,
                min_disk_free_gb=5.0,
                verbose=True,
                quiet=False,
            )

        run_once.assert_called_once_with(
            continue_loop=True,
            verbose=True,
            quiet=False,
        )
        start_write.assert_called_once()
        run_start_write.assert_called_once()
        run_result_write.assert_called_once()
        stop_write.assert_called_once()
        sleep_mock.assert_called_once_with(43_200.0)

    def test_schedule_writes_runtime_status_heartbeat(self) -> None:
        snapshot = ResourceSnapshot(
            load_1m=0.2,
            cpu_count=8,
            memory_available_mb=12_288.0,
            memory_total_mb=16_000.0,
            disk_free_gb=256.0,
            disk_total_gb=512.0,
        )

        with self.subTest("success path writes sleeping/up heartbeat"):
            with unittest.mock.patch.dict("os.environ", {}, clear=False):
                from tempfile import TemporaryDirectory

                with TemporaryDirectory() as tmpdir:
                    status_path = Path(tmpdir) / "scheduler.json"
                    with (
                        patch.dict("os.environ", {"ANTIGRAVITY_EVOSKILL_HEARTBEAT_FILE": str(status_path)}, clear=False),
                        patch("src.cli.commands.schedule._find_project_root", return_value=Path("/tmp/project")),
                        patch("src.cli.commands.schedule.sample_resource_snapshot", return_value=snapshot),
                        patch("src.cli.commands.schedule.seconds_until", return_value=43_200.0),
                        patch(
                            "src.cli.commands.schedule.run_evoskill_once",
                            return_value=SimpleNamespace(
                                run_id="run-123",
                                project_root=Path("/tmp/project"),
                            ),
                        ),
                        patch(
                            "src.cli.commands.schedule.record_watchdog_supervisor_start",
                            return_value=SimpleNamespace(status="ok", detail=None),
                        ),
                        patch(
                            "src.cli.commands.schedule.record_watchdog_supervisor_run_start",
                            return_value=SimpleNamespace(status="ok", detail=None),
                        ),
                        patch(
                            "src.cli.commands.schedule.record_watchdog_supervisor_run_result",
                            return_value=SimpleNamespace(status="ok", detail=None),
                        ),
                        patch(
                            "src.cli.commands.schedule.record_watchdog_supervisor_stop",
                            return_value=SimpleNamespace(status="ok", detail=None),
                        ),
                        patch("src.cli.commands.schedule.time.sleep", side_effect=KeyboardInterrupt),
                    ):
                        schedule_cmd.callback(
                            interval_hours=12.0,
                            min_free_memory_mb=2_048.0,
                            max_load_per_cpu=1.5,
                            min_disk_free_gb=5.0,
                            verbose=False,
                            quiet=True,
                        )

                    payload = json.loads(status_path.read_text(encoding="utf-8"))
                    self.assertEqual(payload["status"], "down")
                    self.assertEqual(payload["mode"], "stopped")
                    self.assertEqual(payload["cycle"], 1)


if __name__ == "__main__":
    unittest.main()
