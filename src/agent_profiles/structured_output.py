"""Helpers for validating and lightly repairing structured agent output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def _extract_balanced_json(text: str, opener: str, closer: str) -> str | None:
    """Return the first balanced JSON substring for a brace pair."""
    start = text.find(opener)
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json_candidate(text: str) -> str | None:
    """Extract a likely JSON object/array from free-form assistant text."""
    stripped = str(text or "").strip()
    if not stripped:
        return None

    if stripped.startswith("{") or stripped.startswith("["):
        return stripped

    fenced_index = stripped.lower().find("```json")
    if fenced_index >= 0:
        fenced_body = stripped[fenced_index + len("```json") :]
        closing_index = fenced_body.find("```")
        if closing_index >= 0:
            candidate = fenced_body[:closing_index].strip()
            if candidate:
                return candidate

    for opener, closer in (("{", "}"), ("[", "]")):
        candidate = _extract_balanced_json(stripped, opener, closer)
        if candidate:
            return candidate
    return None


def _validate_candidate(response_model: type[T], candidate: Any) -> T:
    if isinstance(candidate, BaseModel):
        candidate = candidate.model_dump()
    if isinstance(candidate, Mapping):
        return response_model.model_validate(dict(candidate))
    if isinstance(candidate, str):
        return response_model.model_validate_json(candidate)
    return response_model.model_validate(candidate)


def coerce_structured_output(
    response_model: type[T],
    raw_structured_output: Any | None,
    *,
    result_text: str | None = None,
) -> tuple[T | None, str | None, bool]:
    """Validate structured output and try a thin text-to-JSON repair when needed.

    Returns:
        A tuple of (validated_output, parse_error, repaired_from_text).
    """
    sources: list[tuple[str, Any]] = []
    if raw_structured_output is not None:
        sources.append(("structured_output", raw_structured_output))
    if result_text:
        sources.append(("result_text", result_text))

    if not sources:
        return None, "No structured output returned (context limit likely exceeded)", False

    last_error: str | None = None
    for source_name, payload in sources:
        candidates: list[Any] = [payload]
        if isinstance(payload, str):
            extracted = extract_json_candidate(payload)
            if extracted and extracted != payload:
                candidates.append(extracted)

        for candidate in candidates:
            try:
                output = _validate_candidate(response_model, candidate)
                native_structured = source_name == "structured_output" and isinstance(
                    payload, (BaseModel, Mapping)
                )
                repaired = (not native_structured) or candidate is not payload
                return output, None, repaired
            except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
                last_error = f"{source_name}: {type(exc).__name__}: {exc}"

    if last_error:
        return None, f"Unable to coerce structured output: {last_error}", False
    return None, "Unable to coerce structured output", False
