from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent_profiles.structured_output import coerce_structured_output


class DemoOutput(BaseModel):
    action: Literal["create", "edit"]
    proposed_skill: str
    justification: str


class StructuredOutputTests(unittest.TestCase):
    def test_valid_dict_is_accepted_without_repair(self) -> None:
        output, parse_error, repaired = coerce_structured_output(
            DemoOutput,
            {
                "action": "create",
                "proposed_skill": "local inference repair",
                "justification": "Keep shape checks separate from content quality.",
            },
        )

        self.assertIsNotNone(output)
        self.assertIsNone(parse_error)
        self.assertFalse(repaired)
        self.assertEqual(output.proposed_skill, "local inference repair")

    def test_json_fence_is_repaired_from_text(self) -> None:
        text = """
        Here is the structured response:

        ```json
        {
          "action": "edit",
          "proposed_skill": "schema-aware repair",
          "justification": "Recover the model output when it is JSON-shaped but wrapped in prose."
        }
        ```
        """

        output, parse_error, repaired = coerce_structured_output(
            DemoOutput,
            None,
            result_text=text,
        )

        self.assertIsNotNone(output)
        self.assertIsNone(parse_error)
        self.assertTrue(repaired)
        self.assertEqual(output.action, "edit")

    def test_prose_without_json_still_fails_cleanly(self) -> None:
        output, parse_error, repaired = coerce_structured_output(
            DemoOutput,
            None,
            result_text="The model explained the idea but never emitted JSON.",
        )

        self.assertIsNone(output)
        self.assertIsNotNone(parse_error)
        self.assertFalse(repaired)
        self.assertIn("Unable", parse_error or "")


if __name__ == "__main__":
    unittest.main()
