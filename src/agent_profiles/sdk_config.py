"""SDK configuration and selection logic.

This module provides a global setting to choose between OpenCode and
Gemini-backed execution paths.
"""

from typing import Literal

SDKType = Literal["opencode", "gemini"]

# Global SDK selection (can be overridden via CLI arguments)
_current_sdk: SDKType = "gemini"
_current_model: str | None = None


def set_sdk(sdk: SDKType, model: str | None = None) -> None:
    """Set the current SDK and optional model to use globally."""
    global _current_sdk, _current_model
    if sdk not in ("opencode", "gemini"):
        raise ValueError(
            f"Invalid SDK type: {sdk}. Must be 'opencode' or 'gemini'"
        )
    _current_sdk = sdk
    _current_model = model


def get_sdk() -> SDKType:
    """Get the currently configured SDK."""
    return _current_sdk


def get_model() -> str | None:
    """Get the currently configured model, if any."""
    return _current_model


def is_claude_sdk() -> bool:
    """Check if claude-agent-sdk is the current SDK."""
    return _current_sdk == "claude"


def is_opencode_sdk() -> bool:
    """Check if opencode-ai is the current SDK."""
    return _current_sdk == "opencode"


def is_gemini_sdk() -> bool:
    """Check if Gemini CLI is the current SDK."""
    return _current_sdk == "gemini"
