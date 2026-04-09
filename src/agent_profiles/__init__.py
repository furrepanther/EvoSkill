"""Lazy exports for EvoSkill agent profiles."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "proposer_options": (".proposer", "proposer_options"),
    "skill_generator_options": (".skill_generator", "skill_generator_options"),
    "base_agent_options": (".base_agent", "base_agent_options"),
    "make_base_agent_options": (".base_agent", "make_base_agent_options"),
    "dabstep_agent_options": (".dabstep_agent", "dabstep_agent_options"),
    "make_dabstep_agent_options": (".dabstep_agent", "make_dabstep_agent_options"),
    "sealqa_agent_options": (".sealqa_agent", "sealqa_agent_options"),
    "make_sealqa_agent_options": (".sealqa_agent", "make_sealqa_agent_options"),
    "livecodebench_agent_options": (".livecodebench_agent", "livecodebench_agent_options"),
    "make_livecodebench_agent_options": (".livecodebench_agent", "make_livecodebench_agent_options"),
    "prompt_generator_options": (".prompt_generator", "prompt_generator_options"),
    "skill_proposer_options": (".skill_proposer", "skill_proposer_options"),
    "prompt_proposer_options": (".prompt_proposer", "prompt_proposer_options"),
    "Agent": (".base", "Agent"),
    "AgentTrace": (".base", "AgentTrace"),
    "set_sdk": (".sdk_config", "set_sdk"),
    "get_sdk": (".sdk_config", "get_sdk"),
    "get_model": (".sdk_config", "get_model"),
    "is_opencode_sdk": (".sdk_config", "is_opencode_sdk"),
    "is_gemini_sdk": (".sdk_config", "is_gemini_sdk"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})


__all__ = list(_LAZY_EXPORTS)
