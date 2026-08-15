from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_constant(path: Path, attribute: str) -> str:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load prompt module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = getattr(module, attribute)
    if not isinstance(value, str):
        raise TypeError(f"{attribute} from {path} is not a string")
    return value


PROPOSER_SYSTEM_PROMPT = _load_constant(
    ROOT / "src" / "agent_profiles" / "proposer" / "prompt.py",
    "PROPOSER_SYSTEM_PROMPT",
)
PROMPT_PROPOSER_SYSTEM_PROMPT = _load_constant(
    ROOT / "src" / "agent_profiles" / "prompt_proposer" / "prompt.py",
    "PROMPT_PROPOSER_SYSTEM_PROMPT",
)
SKILL_PROPOSER_SYSTEM_PROMPT = _load_constant(
    ROOT / "src" / "agent_profiles" / "skill_proposer" / "prompt.py",
    "SKILL_PROPOSER_SYSTEM_PROMPT",
)


class PromptOutputContractTests(unittest.TestCase):
    def test_skill_proposer_prompt_requires_json_only(self) -> None:
        self.assertIn("Output in JSON format only", SKILL_PROPOSER_SYSTEM_PROMPT)
        self.assertIn('"action": "create" | "edit"', SKILL_PROPOSER_SYSTEM_PROMPT)
        self.assertIn('"related_iterations"', SKILL_PROPOSER_SYSTEM_PROMPT)

    def test_prompt_proposer_prompt_requires_json_only(self) -> None:
        self.assertIn("Output in JSON format only", PROMPT_PROPOSER_SYSTEM_PROMPT)
        self.assertIn('"proposed_prompt_change"', PROMPT_PROPOSER_SYSTEM_PROMPT)
        self.assertIn('"justification"', PROMPT_PROPOSER_SYSTEM_PROMPT)

    def test_generic_proposer_prompt_requires_json_only(self) -> None:
        self.assertIn("Output in JSON format only", PROPOSER_SYSTEM_PROMPT)
        self.assertIn('"optimize_prompt_or_skill"', PROPOSER_SYSTEM_PROMPT)
        self.assertIn('"proposed_skill_or_prompt"', PROPOSER_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
