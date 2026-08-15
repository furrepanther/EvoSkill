from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

from src.evoskill_memory import publish_evoskill_run_memory


@dataclass
class SkillLike:
    name: str
    iteration: int
    score_delta: float
    action: str


class FakeMemfabClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, tool_name: str, payload: dict) -> dict:
        self.calls.append((tool_name, payload))
        return {
            "status": "ok",
            "detail": f"stored {tool_name}",
            "fingerprint_key": f"fp-{len(self.calls)}",
        }

    def extract_tool_payload(self, response: dict) -> dict:
        return response


class EvoSkillMemoryTests(unittest.TestCase):
    def test_publish_run_writes_family_and_skill_records(self) -> None:
        client = FakeMemfabClient()
        project_root = Path("/tmp/evoskill-test")
        report_path = project_root / ".evoskill" / "reports" / "run-abc.md"
        telemetry_path = project_root / ".evoskill" / "telemetry" / "run-abc.json"

        results = publish_evoskill_run_memory(
            run_id="run-abc",
            project_root=project_root,
            best_program="program/iter-skill-3",
            baseline_score=0.25,
            final_score=0.5,
            iterations_completed=3,
            total_cost_usd=1.2345,
            skills_kept=[
                SkillLike(
                    name="watchdog_supervisor",
                    iteration=3,
                    score_delta=0.25,
                    action="edit",
                )
            ],
            report_path=report_path,
            telemetry_path=telemetry_path,
            client=client,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual([result.record_type for result in results], [
            "evoskill_family_complete",
            "evoskill_skill_complete",
        ])
        self.assertTrue(all(result.status == "ok" for result in results))
        self.assertEqual(len(client.calls), 2)

        family_content = client.calls[0][1]["content"]
        self.assertIn("family: evoskill_run", family_content)
        self.assertIn("record_type: evoskill_family_complete", family_content)
        self.assertIn("best_program=program/iter-skill-3", family_content)
        self.assertIn(str(report_path), family_content)
        self.assertIn(str(telemetry_path), family_content)

        skill_content = client.calls[1][1]["content"]
        self.assertIn("record_type: evoskill_skill_complete", skill_content)
        self.assertIn("family: evoskill_run", skill_content)
        self.assertIn("skill_name=watchdog_supervisor", skill_content)
        self.assertIn("action=edit", skill_content)
        self.assertIn("iteration=3", skill_content)
        self.assertIn(str(project_root / ".claude" / "skills" / "watchdog_supervisor" / "SKILL.md"), skill_content)


if __name__ == "__main__":
    unittest.main()
