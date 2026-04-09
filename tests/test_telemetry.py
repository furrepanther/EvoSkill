from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent_profiles.base import AgentTrace
from src.telemetry import RunTelemetry, make_run_id, trace_to_snapshot


class DemoOutput(BaseModel):
    final_answer: str


def make_trace(*, result: str = "answer " * 50) -> AgentTrace[DemoOutput]:
    return AgentTrace(
        uuid="trace-1",
        session_id="session-1",
        model="demo-model",
        tools=["tool-a", "tool-b"],
        duration_ms=123,
        total_cost_usd=0.42,
        num_turns=3,
        usage={"input_tokens": 10, "output_tokens": 5},
        result=result,
        is_error=False,
        output=DemoOutput(final_answer="ok"),
        structured_output_repaired=False,
        parse_error=None,
        raw_structured_output={"final_answer": "ok"},
        messages=[],
    )


class TelemetryTests(unittest.TestCase):
    def test_trace_snapshot_truncates_and_keeps_output(self) -> None:
        snapshot = trace_to_snapshot(make_trace(), result_chars=24)
        self.assertTrue(snapshot.result_excerpt.endswith("[truncated]"))
        self.assertEqual(snapshot.output, {"final_answer": "ok"})
        self.assertFalse(snapshot.structured_output_repaired)

    def test_run_telemetry_preserves_payload_and_extra_fields(self) -> None:
        telemetry = RunTelemetry.create(
            run_id=make_run_id(),
            project_root=Path("/tmp/evoskill"),
            task_name="demo",
            task_description="desc",
            task_constraints="constraints",
            dataset_path=Path("/tmp/evoskill/data.csv"),
            harness="claude",
            model="sonnet",
            evolution_mode="skill_only",
            iterations_requested=3,
            frontier_size=2,
            concurrency=4,
            failure_samples=2,
            train_ratio=0.5,
            val_ratio=0.5,
            dataset_summary={"train_counts": {"a": 2}},
        )

        event = telemetry.add_event(
            "sample",
            iteration=7,
            total=3,
            category="alpha",
            question="Why?",
            agent_answer="Because",
            ground_truth="Because",
            score=1.0,
            passed=True,
            trace=make_trace(),
            unexpected="kept",
        )

        self.assertEqual(event.iteration, 7)
        self.assertEqual(event.total, 3)
        self.assertIsNotNone(event.trace)
        self.assertEqual(event.trace.result_excerpt, trace_to_snapshot(make_trace(), result_chars=1_200).result_excerpt)
        self.assertEqual(event.extra["unexpected"], "kept")

    def test_run_telemetry_round_trips_to_disk(self) -> None:
        telemetry = RunTelemetry.create(
            run_id=make_run_id(),
            project_root=Path("/tmp/evoskill"),
            task_name="demo",
            task_description="desc",
            task_constraints="constraints",
            dataset_path=Path("/tmp/evoskill/data.csv"),
            harness="claude",
            model="sonnet",
            evolution_mode="skill_only",
            iterations_requested=3,
            frontier_size=2,
            concurrency=4,
            failure_samples=2,
            train_ratio=0.5,
            val_ratio=0.5,
        )
        telemetry.finalize(
            baseline_score=0.25,
            final_score=0.75,
            best_program="base",
            iterations_completed=2,
            total_cost_usd=1.23,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "run.json"
            telemetry.save(path)
            loaded = RunTelemetry.load(path)

        self.assertEqual(loaded.run_id, telemetry.run_id)
        self.assertEqual(loaded.baseline_score, 0.25)
        self.assertEqual(loaded.final_score, 0.75)
        self.assertEqual(loaded.best_program, "base")


if __name__ == "__main__":
    unittest.main()
