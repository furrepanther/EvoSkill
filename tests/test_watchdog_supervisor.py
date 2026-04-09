from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.watchdog_supervisor import (
    record_watchdog_supervisor_run_result,
    record_watchdog_supervisor_run_start,
    record_watchdog_supervisor_start,
    record_watchdog_supervisor_stop,
)


class FakeMemfabClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"ok": True}

    def extract_tool_payload(self, response: dict[str, object]) -> dict[str, object]:
        return self.payload


class WatchdogSupervisorTests(unittest.TestCase):
    def test_start_and_stop_write_memory_fabric_events(self) -> None:
        client = FakeMemfabClient({"status": "ok", "fingerprint_key": "fp-start"})

        start_result = record_watchdog_supervisor_start(
            interval_hours=12.0,
            min_free_memory_mb=2_048.0,
            max_load_per_cpu=1.5,
            min_disk_free_gb=5.0,
            observed_at_utc="2026-04-07T12:00:00+00:00",
            client=client,
        )
        stop_result = record_watchdog_supervisor_stop(
            cycle=3,
            reason="keyboard_interrupt",
            observed_at_utc="2026-04-07T12:00:10+00:00",
            client=client,
        )

        self.assertEqual(start_result.status, "ok")
        self.assertEqual(stop_result.status, "ok")
        self.assertEqual(client.calls[0][0], "memory_store")
        self.assertIn("event_type: watchdog_supervisor_start", client.calls[0][1]["content"])
        self.assertIn("source_tool: watchdog_supervisor", client.calls[0][1]["content"])
        self.assertIn("twice-daily", client.calls[0][1]["content"])
        self.assertIn("event_type: watchdog_supervisor_stop", client.calls[1][1]["content"])

    def test_run_result_includes_report_evidence(self) -> None:
        client = FakeMemfabClient({"status": "ok", "fingerprint_key": "fp-result"})
        snapshot = SimpleNamespace(
            load_1m=0.5,
            cpu_count=8,
            memory_available_mb=8_192.0,
            disk_free_gb=128.0,
        )
        report = SimpleNamespace(
            run_id="run-123",
            project_root=Path("/tmp/project"),
            baseline_score=0.4,
            final_score=0.6,
            total_cost_usd=1.23,
        )

        result = record_watchdog_supervisor_run_result(
            cycle=2,
            status="success",
            started_at_utc="2026-04-07T12:00:00+00:00",
            completed_at_utc="2026-04-07T12:05:00+00:00",
            next_run_utc="2026-04-08T00:00:00+00:00",
            resource_snapshot=snapshot,
            report=report,
            observed_at_utc="2026-04-07T12:05:00+00:00",
            client=client,
        )

        self.assertEqual(result.status, "ok")
        content = client.calls[0][1]["content"]
        self.assertIn("event_type: watchdog_supervisor_run_result", content)
        self.assertIn("run_id=run-123", content)
        self.assertIn("baseline=40.0%", content)
        self.assertIn("final=60.0%", content)
        self.assertIn("/tmp/project/.evoskill/reports/run-run-123.md", content)
        self.assertIn("/tmp/project/.evoskill/telemetry/run-run-123.json", content)

    def test_run_start_records_cycle_boundary(self) -> None:
        client = FakeMemfabClient({"status": "ok"})
        snapshot = SimpleNamespace(
            load_1m=32.0,
            cpu_count=2,
            memory_available_mb=256.0,
            disk_free_gb=2.0,
        )

        result = record_watchdog_supervisor_run_start(
            cycle=4,
            started_at_utc="2026-04-07T12:00:00+00:00",
            next_run_utc="2026-04-08T00:00:00+00:00",
            resource_snapshot=snapshot,
            observed_at_utc="2026-04-07T12:00:00+00:00",
            client=client,
        )

        self.assertEqual(result.status, "ok")
        content = client.calls[0][1]["content"]
        self.assertIn("event_type: watchdog_supervisor_run_start", content)
        self.assertIn("cycle 4", content.lower())
        self.assertIn("load=32.00/2", content)


if __name__ == "__main__":
    unittest.main()
