"""Local compatibility stub for environments that do not use Claude SDK.

This keeps import-time references from blocking Gemini-backed EvoSkill flows
while still failing loudly if someone actually tries to execute a Claude path.
"""

from __future__ import annotations


class ClaudeAgentOptions:
    """Lightweight attribute bag matching the parts EvoSkill reads."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class ClaudeSDKClient:
    """Disabled in this environment."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "Claude SDK execution is disabled in this environment; use the Gemini-backed EvoSkill path instead."
        )
