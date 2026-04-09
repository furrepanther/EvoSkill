"""EvoSkill public package exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "FeedbackDescent": (".feedback_descent", "FeedbackDescent"),
    "EvaluationResult": (".feedback_descent", "EvaluationResult"),
    "FeedbackEntry": (".feedback_descent", "FeedbackEntry"),
    "FeedbackDescentResult": (".feedback_descent", "FeedbackDescentResult"),
    "Proposer": (".feedback_descent", "Proposer"),
    "Evaluator": (".feedback_descent", "Evaluator"),
    "EvoSkill": (".api", "EvoSkill"),
    "EvalRunner": (".api", "EvalRunner"),
    "EvalSummary": (".api", "EvalSummary"),
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
