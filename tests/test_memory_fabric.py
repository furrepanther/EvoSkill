from __future__ import annotations

import unittest
from pathlib import Path
import sys

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loop.helpers import build_memory_retrieval_query, build_proposer_query
from src.memory_fabric import retrieve_memory_fabric_context, render_memory_fabric_context


class DemoOutput(BaseModel):
    final_answer: str


class StubTrace:
    def __init__(self) -> None:
        self.model = "demo-model"
        self.num_turns = 2
        self.duration_ms = 75
        self.is_error = False
        self.parse_error = None
        self.output = DemoOutput(final_answer="ok")
        self.result = "watchdog supervisor exited when the monitored service failed"

    def summarize(self, head_chars: int = 60_000, tail_chars: int = 60_000) -> str:
        return f"TRACE[{head_chars}:{tail_chars}] {self.result}"


class FakeMemfabClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"ok": True}

    def extract_tool_payload(self, response: dict[str, object]) -> dict[str, object]:
        return self.payload


class MemoryFabricTests(unittest.TestCase):
    def test_retrieve_memory_context_normalizes_hits(self) -> None:
        client = FakeMemfabClient(
            {
                "results": [
                    {
                        "title": "Watchdog restart regression",
                        "summary": "watchdog_supervisor exited because of a launch flag mismatch",
                        "score": 0.91,
                        "source": "memory_note",
                        "memory_id": "mem-1",
                        "tags": ["watchdog", "startup"],
                    }
                ]
            }
        )

        retrieval = retrieve_memory_fabric_context(
            "watchdog crash model mismatch",
            client=client,
        )

        self.assertEqual(retrieval.status, "ok")
        self.assertEqual(retrieval.hit_count, 1)
        self.assertEqual(client.calls[0][0], "memory_retrieve")
        self.assertIn("watchdog", client.calls[0][1]["query"])

        rendered = render_memory_fabric_context(retrieval)
        self.assertIn("## Memory Fabric Context", rendered)
        self.assertIn("Watchdog restart regression", rendered)
        self.assertIn("source=memory_note", rendered)

    def test_build_memory_retrieval_query_uses_failure_context(self) -> None:
        trace = StubTrace()
        query = build_memory_retrieval_query(
            [(trace, "it crashed", "it should run", "startup")],
            "No previous attempts.\n## 1\n**Proposal**: improve watchdog",
            evolution_mode="skill_only",
            task_constraints="Keep startup robust.",
        )

        self.assertIn("## Retrieval Goal", query)
        self.assertIn("Keep startup robust.", query)
        self.assertIn("watchdog", query)
        self.assertIn("startup", query)
        self.assertIn("Current Skills", query)

    def test_build_proposer_query_includes_memory_section(self) -> None:
        trace = StubTrace()
        retrieval = retrieve_memory_fabric_context(
            "watchdog crash model mismatch",
            client=FakeMemfabClient(
                {
                    "results": [
                        {
                            "title": "Watchdog restart regression",
                            "summary": "launch flag mismatch killed the supervisor",
                        }
                    ]
                }
            ),
        )
        memory_section = render_memory_fabric_context(retrieval)
        query = build_proposer_query(
            [(trace, "it crashed", "it should run", "startup")],
            "No previous attempts.",
            memory_context_section=memory_section,
        )

        self.assertIn("## Memory Fabric Context", query)
        self.assertIn("Watchdog restart regression", query)
        self.assertIn("## Existing Skills", query)


if __name__ == "__main__":
    unittest.main()
