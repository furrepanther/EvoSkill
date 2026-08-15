from typing import Any

from src.agent_profiles.skill_generator import get_project_root
from src.schemas import AgentResponse


# Use full tool suite for LiveCodeBench (agent can use tools to test/debug)
LIVECODEBENCH_AGENT_TOOLS = [
    "Read",
    "Write",
    "Bash",
    "Glob",
    "Grep",
    "Edit",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "BashOutput",
    "Skill",
]

# NOTE: Question formatting (in livecodebench_format.py) matches Artificial Analysis.
# The runtime uses the generic default prompt/tooling path for evaluation.
# Reference: https://artificialanalysis.ai/benchmarks/livecodebench


def get_livecodebench_agent_options(
    model: str | None = None,
) -> dict[str, Any]:
    """
    Factory function that creates agent options for LiveCodeBench evaluation.

    Uses the generic runtime prompt and full tool access.

    Args:
        model: Model to use (e.g., "opus", "sonnet"). If None, uses SDK default.
    """
    return {
        "system": "",
        "format": {
            "type": "json_schema",
            "schema": AgentResponse.model_json_schema(),
        },
        "tools": {tool: True for tool in LIVECODEBENCH_AGENT_TOOLS},
        "mode": "build",
        "model_id": model or "deepseek-ai/DeepSeek-V3",
        "provider_id": "togetherai",
    }


def make_livecodebench_agent_options(model: str | None = None):
    """Create a factory function for LiveCodeBench agent options with a specific model.

    Args:
        model: Model to use (e.g., "opus", "sonnet"). If None, uses SDK default.

    Returns:
        A callable that returns runtime agent options configured with the model.
    """

    def factory() -> dict[str, Any]:
        return get_livecodebench_agent_options(model=model)

    return factory


# For backward compatibility, expose the factory as the options
livecodebench_agent_options = get_livecodebench_agent_options
