"""
Utilities for converting between ProgramConfig and agent SDK payloads.

These helpers allow seamless integration between the program registry
and whichever agent runtime consumes the payload.
"""

import os
from datetime import datetime
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions as SDKAgentOptions

from .models import ProgramConfig


def config_to_options(
    config: ProgramConfig,
    cwd: str,
    *,
    add_dirs: list[Any] | None = None,
    permission_mode: str = "acceptEdits",
) -> SDKAgentOptions:
    """
    Convert ProgramConfig to agent SDK options.

    Args:
        config: The program configuration
        cwd: Working directory for the agent
        add_dirs: Additional directories to add to agent context
        permission_mode: Permission mode for tool execution

    Returns:
        Agent SDK options ready for use by the runtime client
    """
    return SDKAgentOptions(
        system_prompt=config.system_prompt,
        allowed_tools=config.allowed_tools,
        output_format=config.output_format,
        setting_sources=["user", "project"],  # Load skills from the project skill directory.
        permission_mode=permission_mode,
        add_dirs=add_dirs or [],
        cwd=cwd,
    )


def options_to_config(
    options: SDKAgentOptions,
    name: str,
    *,
    parent: str | None = None,
    generation: int = 0,
    metadata: dict[str, Any] | None = None,
) -> ProgramConfig:
    """
    Convert agent SDK options to ProgramConfig.

    Args:
        options: The agent options to convert
        name: Name for the program
        parent: Parent program reference (e.g., 'program/base')
        generation: Number of mutations from base
        metadata: Additional metadata to include

    Returns:
        ProgramConfig ready for registration
    """
    base_metadata = {"created_at": datetime.now().isoformat()}
    if metadata:
        base_metadata.update(metadata)

    return ProgramConfig(
        name=name,
        parent=parent,
        generation=generation,
        system_prompt=options.system_prompt or {},
        allowed_tools=options.allowed_tools or [],
        output_format=options.output_format,
        metadata=base_metadata,
    )


def _system_prompt_to_text(system_prompt: Any) -> str:
    if isinstance(system_prompt, str):
        return system_prompt.strip()
    if not isinstance(system_prompt, dict):
        return ""

    parts: list[str] = []
    prepend = str(system_prompt.get("prepend", "")).strip()
    append = str(system_prompt.get("append", "")).strip()
    if prepend:
        parts.append(prepend)
    if append:
        parts.append(append)
    return "\n\n".join(parts).strip()


def options_to_runtime_config(
    options: Any,
    *,
    fallback_model: str | None = None,
    fallback_provider_id: str | None = None,
) -> dict[str, Any]:
    """
    Convert SDK options into a runtime-compatible dict payload.

    Object-shaped options are normalized so the runtime execution path can stay
    generic and avoid hard failures when a non-dict options object is supplied.
    """
    if isinstance(options, dict):
        return dict(options)

    payload: dict[str, Any] = {}

    system_prompt = getattr(options, "system_prompt", None)
    system_text = _system_prompt_to_text(system_prompt)
    if system_text:
        payload["system"] = system_text

    output_format = getattr(options, "output_format", None)
    if output_format is not None:
        payload["format"] = output_format

    allowed_tools = getattr(options, "allowed_tools", None) or []
    payload["tools"] = {str(tool): True for tool in allowed_tools}

    mode = getattr(options, "mode", None)
    if mode:
        payload["mode"] = str(mode)

    model_id = getattr(options, "model", None) or fallback_model
    if model_id:
        payload["model_id"] = str(model_id)

    provider_id = getattr(options, "provider_id", None) or fallback_provider_id
    if provider_id is None:
        provider_id = os.getenv("OPENCODE_PROVIDER_ID", "togetherai")
    if provider_id:
        payload["provider_id"] = str(provider_id)

    return payload


def merge_system_prompt(
    base: dict[str, Any],
    *,
    append: str | None = None,
    prepend: str | None = None,
) -> dict[str, Any]:
    """
    Create a modified system prompt by appending/prepending content.

    Args:
        base: Base system prompt configuration
        append: Text to append to the prompt
        prepend: Text to prepend to the prompt

    Returns:
        New system prompt dict with modifications
    """
    result = dict(base)

    if append:
        existing_append = result.get("append", "")
        if existing_append:
            result["append"] = f"{existing_append}\n\n{append}"
        else:
            result["append"] = append

    if prepend:
        existing_append = result.get("append", "")
        if existing_append:
            result["append"] = f"{prepend}\n\n{existing_append}"
        else:
            result["append"] = prepend

    return result


def add_tools(config: ProgramConfig, tools: list[str]) -> ProgramConfig:
    """
    Create a new config with additional tools.

    Args:
        config: Base program configuration
        tools: Tools to add

    Returns:
        New ProgramConfig with additional tools
    """
    new_tools = list(set(config.allowed_tools + tools))
    return config.model_copy(update={"allowed_tools": new_tools})


def remove_tools(config: ProgramConfig, tools: list[str]) -> ProgramConfig:
    """
    Create a new config with tools removed.

    Args:
        config: Base program configuration
        tools: Tools to remove

    Returns:
        New ProgramConfig without specified tools
    """
    new_tools = [t for t in config.allowed_tools if t not in tools]
    return config.model_copy(update={"allowed_tools": new_tools})
