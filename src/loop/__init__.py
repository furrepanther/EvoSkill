"""Lazy exports for the self-improving agent loop."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "LoopConfig": (".config", "LoopConfig"),
    "SelfImprovingLoop": (".runner", "SelfImprovingLoop"),
    "LoopAgents": (".runner", "LoopAgents"),
    "LoopResult": (".runner", "LoopResult"),
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
