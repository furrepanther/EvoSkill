from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_run_command_imports_without_external_claude_sdk() -> None:
    from src.cli.commands.run import run_cmd

    assert run_cmd.name == "run"
