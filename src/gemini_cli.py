"""Gemini CLI integration helpers.

These helpers run the Google Gemini CLI in headless mode, using the cached
Google login stored by Gemini CLI under ``~/.gemini``. They are intentionally
thin so the rest of EvoSkill can treat Gemini like a normal model backend.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

GEMINI_DEFAULT_MODEL = "gemini-3.1-pro-preview"
GEMINI_MODEL_PREFERENCE = (
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
)
GEMINI_CLI_REPO = Path("/mnt/f/Github/gemini-cli")


@dataclass(frozen=True)
class GeminiCLIResult:
    """Structured output from a Gemini CLI invocation."""

    response: str
    stats: dict[str, Any]
    raw: dict[str, Any]
    duration_ms: int
    command: tuple[str, ...]


@dataclass(frozen=True)
class GeminiQuotaBucket:
    """Quota information for a single Gemini model."""

    model: str
    remaining_amount: int | None
    remaining_fraction: float | None
    reset_time: str | None


@dataclass(frozen=True)
class GeminiQuotaProbe:
    """Structured quota snapshot returned from Gemini CLI."""

    fetched: bool
    buckets: dict[str, GeminiQuotaBucket]
    raw: dict[str, Any]
    duration_ms: int
    command: tuple[str, ...]


@dataclass(frozen=True)
class GeminiModelCandidate:
    """A preferred Gemini model plus its quota state."""

    model: str
    status: str
    remaining_amount: int | None
    remaining_fraction: float | None
    reset_time: str | None


@dataclass(frozen=True)
class GeminiModelSelection:
    """Selected Gemini model and the quota evidence used to pick it."""

    selected_model: str
    candidates: tuple[GeminiModelCandidate, ...]
    quota_probe: GeminiQuotaProbe
    reason: str


def normalize_gemini_model(model: str | None) -> str:
    """Normalize a model name for Gemini CLI."""
    candidate = (model or "").strip()
    if not candidate:
        return GEMINI_DEFAULT_MODEL

    lowered = candidate.lower()
    if lowered in {"auto", "pro", "flash", "flash-lite"}:
        return candidate
    if lowered.startswith("gemini-"):
        return candidate
    return GEMINI_DEFAULT_MODEL


def build_gemini_model_chain(requested_model: str | None = None) -> tuple[str, ...]:
    """Build the preferred Gemini model chain with an optional explicit model first."""
    chain = list(GEMINI_MODEL_PREFERENCE)
    if requested_model:
        explicit = requested_model.strip()
        if explicit.startswith("gemini-") and explicit not in chain:
            chain.insert(0, explicit)

    deduped: list[str] = []
    for candidate in chain:
        if candidate not in deduped:
            deduped.append(candidate)
    return tuple(deduped)


def resolve_gemini_command() -> list[str]:
    """Resolve a local Gemini CLI executable or raise if unavailable."""
    override = os.environ.get("EVOSKILL_GEMINI_CLI")
    if override:
        return [override]

    gemini_bin = shutil.which("gemini")
    if gemini_bin:
        return [gemini_bin]

    local_bin = GEMINI_CLI_REPO / "node_modules" / ".bin" / "gemini"
    if local_bin.exists():
        return [str(local_bin)]

    local_bundle = GEMINI_CLI_REPO / "bundle" / "gemini.js"
    if local_bundle.exists():
        return ["node", str(local_bundle)]

    raise RuntimeError(
        "Gemini CLI is not installed locally. Set EVOSKILL_GEMINI_CLI, "
        "add gemini to PATH, or build /mnt/f/Github/gemini-cli so "
        "bundle/gemini.js exists."
    )


def extract_gemini_system_prompt(options: Any) -> str:
    """Extract a Gemini-friendly system prompt from agent options."""
    system_prompt: Any = None
    if isinstance(options, dict):
        system_prompt = options.get("system") or options.get("system_prompt")
    else:
        system_prompt = getattr(options, "system_prompt", None)

    if not system_prompt:
        return ""

    if isinstance(system_prompt, str):
        return system_prompt.strip()

    if isinstance(system_prompt, dict):
        append = system_prompt.get("append")
        if append:
            return str(append).strip()
        preset = system_prompt.get("preset")
        if preset:
            return str(preset).strip()
        return json.dumps(system_prompt, indent=2, sort_keys=True)

    return str(system_prompt).strip()


def extract_gemini_include_directories(options: Any) -> list[str]:
    """Extract include directories from agent options."""
    directories: Any = []
    if isinstance(options, dict):
        directories = options.get("include_directories") or options.get("add_dirs") or []
    else:
        directories = getattr(options, "add_dirs", None) or []

    return [str(Path(directory).expanduser().resolve()) for directory in directories if directory]


def extract_gemini_cwd(options: Any) -> Path | None:
    """Extract a working directory from agent options."""
    if isinstance(options, dict):
        cwd = options.get("cwd")
    else:
        cwd = getattr(options, "cwd", None)

    if not cwd:
        return None
    return Path(str(cwd)).expanduser().resolve()


def extract_gemini_model(options: Any) -> str | None:
    """Extract a model name from agent options."""
    if isinstance(options, dict):
        model = options.get("model") or options.get("model_id")
    else:
        model = getattr(options, "model", None)

    if not model:
        return None
    return normalize_gemini_model(str(model))


def extract_gemini_tools(options: Any) -> list[str]:
    """Extract a tool list from agent options for telemetry."""
    if isinstance(options, dict):
        tools = options.get("tools", {})
        if isinstance(tools, dict):
            return [str(name) for name in tools.keys()]
        if isinstance(tools, list):
            return [str(name) for name in tools]
        return []

    allowed_tools = getattr(options, "allowed_tools", None) or []
    return [str(name) for name in allowed_tools]


def build_gemini_prompt(system_prompt: str, query: str) -> str:
    """Combine the system prompt and user query for Gemini CLI."""
    system_prompt = system_prompt.strip()
    query = query.strip()
    if system_prompt:
        return f"{system_prompt}\n\n{query}"
    return query


def _is_gemini_bucket_available(bucket: GeminiQuotaBucket | None) -> bool | None:
    if bucket is None:
        return None
    if bucket.remaining_amount is not None:
        return bucket.remaining_amount > 0
    if bucket.remaining_fraction is not None:
        return bucket.remaining_fraction > 0
    return None


def _resolve_gemini_bundle_core_path() -> Path:
    """Locate the installed Gemini CLI bundle core module."""
    command = resolve_gemini_command()
    command_path = Path(command[1] if command[0] == "node" else command[0]).expanduser().resolve()

    bundle_dir = command_path.parent
    core_files = sorted(bundle_dir.glob("core-*.js"))
    if core_files:
        return core_files[0]

    for parent in command_path.parents:
        candidate_bundle = parent / "bundle"
        core_files = sorted(candidate_bundle.glob("core-*.js"))
        if core_files:
            return core_files[0]

    raise RuntimeError(
        "Could not locate the Gemini CLI bundle core module. "
        "Install gemini locally or point EVOSKILL_GEMINI_CLI at a Gemini CLI binary."
    )


async def probe_gemini_quota(
    models: Sequence[str] | None = None,
    *,
    cwd: Path | None = None,
) -> GeminiQuotaProbe:
    """Fetch a quota snapshot for the preferred Gemini models."""
    resolved_models = tuple(models or GEMINI_MODEL_PREFERENCE)
    bundle_core_path = _resolve_gemini_bundle_core_path()
    payload = {
        "bundleCorePath": str(bundle_core_path),
        "models": list(resolved_models),
        "cwd": str(cwd or Path.cwd()),
        "targetDir": str(cwd or Path.cwd()),
    }
    probe_script = (
        "const input = JSON.parse(process.env.EVOSKILL_GEMINI_QUOTA_INPUT);\n"
        "const { Config, AuthType } = await import(input.bundleCorePath);\n"
        "const config = new Config({\n"
        "  sessionId: 'evoskill-gemini-quota',\n"
        "  targetDir: input.targetDir,\n"
        "  debugMode: false,\n"
        "  model: input.models[0] ?? 'gemini-3.1-pro-preview',\n"
        "  cwd: input.cwd,\n"
        "  folderTrust: true,\n"
        "  usageStatisticsEnabled: false,\n"
        "  sandbox: {\n"
        "    enabled: false,\n"
        "    allowedPaths: [],\n"
        "    includeDirectories: [],\n"
        "    networkAccess: true,\n"
        "  },\n"
        "});\n"
        "await config.refreshAuth(AuthType.LOGIN_WITH_GOOGLE);\n"
        "const quota = await config.refreshUserQuota();\n"
        "const buckets = (quota?.buckets ?? []).map((bucket) => ({\n"
        "  modelId: bucket.modelId ?? '',\n"
        "  remainingAmount: bucket.remainingAmount ?? null,\n"
        "  remainingFraction: bucket.remainingFraction ?? null,\n"
        "  resetTime: bucket.resetTime ?? null,\n"
        "}));\n"
        "process.stdout.write(JSON.stringify({ fetched: buckets.length > 0, buckets }));\n"
    )
    env = os.environ.copy()
    env.setdefault("GOOGLE_GENAI_USE_GCA", "true")
    env["EVOSKILL_GEMINI_QUOTA_INPUT"] = json.dumps(payload)

    start = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        "node",
        "--input-type=module",
        "-e",
        probe_script,
        cwd=str(cwd) if cwd is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout_bytes, stderr_bytes = await process.communicate()
    duration_ms = int((time.monotonic() - start) * 1000)
    stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        raise RuntimeError(
            "Gemini quota probe failed "
            f"(exit {process.returncode}). "
            f"stderr={stderr_text or '[empty]'} "
            f"stdout={stdout_text[:500] or '[empty]'}"
        )

    json_text = stdout_text.splitlines()[-1] if stdout_text else ""
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini quota probe returned non-JSON output. "
            f"stdout={stdout_text[:500] or '[empty]'} "
            f"stderr={stderr_text[:500] or '[empty]'}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Gemini quota probe output was not a JSON object.")

    raw_buckets = payload.get("buckets") or []
    buckets: dict[str, GeminiQuotaBucket] = {}
    if isinstance(raw_buckets, list):
        for bucket in raw_buckets:
            if not isinstance(bucket, dict):
                continue
            model_id = str(bucket.get("modelId") or "").strip()
            if not model_id:
                continue
            remaining_amount = bucket.get("remainingAmount")
            remaining_fraction = bucket.get("remainingFraction")
            buckets[model_id] = GeminiQuotaBucket(
                model=model_id,
                remaining_amount=(
                    int(remaining_amount)
                    if remaining_amount not in (None, "")
                    else None
                ),
                remaining_fraction=(
                    float(remaining_fraction)
                    if remaining_fraction not in (None, "")
                    else None
                ),
                reset_time=(
                    str(bucket.get("resetTime"))
                    if bucket.get("resetTime")
                    else None
                ),
            )

    return GeminiQuotaProbe(
        fetched=bool(payload.get("fetched")),
        buckets=buckets,
        raw=payload,
        duration_ms=duration_ms,
        command=("node", "--input-type=module", "-e", probe_script),
    )


def select_gemini_model_from_probe(
    chain: Sequence[str],
    probe: GeminiQuotaProbe,
) -> GeminiModelSelection:
    """Pick the first preferred Gemini model that still has quota."""
    candidates: list[GeminiModelCandidate] = []
    available: list[GeminiModelCandidate] = []
    unknown: list[GeminiModelCandidate] = []

    for model in chain:
        bucket = probe.buckets.get(model)
        status_value = _is_gemini_bucket_available(bucket)
        if status_value is True:
            status = "available"
        elif status_value is False:
            status = "exhausted"
        else:
            status = "unknown"

        candidate = GeminiModelCandidate(
            model=model,
            status=status,
            remaining_amount=bucket.remaining_amount if bucket else None,
            remaining_fraction=bucket.remaining_fraction if bucket else None,
            reset_time=bucket.reset_time if bucket else None,
        )
        candidates.append(candidate)

        if status == "available":
            available.append(candidate)
        elif status == "unknown":
            unknown.append(candidate)

    if not probe.fetched:
        raise RuntimeError(
            "Could not read Gemini quota. Verify that the Gemini CLI login is available."
        )

    if available:
        winner = available[0]
        return GeminiModelSelection(
            selected_model=winner.model,
            candidates=tuple(candidates),
            quota_probe=probe,
            reason="quota available",
        )

    if unknown:
        winner = unknown[0]
        return GeminiModelSelection(
            selected_model=winner.model,
            candidates=tuple(candidates),
            quota_probe=probe,
            reason=f"quota unavailable for {winner.model}; using best-effort fallback",
        )

    raise RuntimeError(
        "No preferred Gemini model has remaining quota. "
        "Wait for quota to reset or choose a different provider."
    )


async def choose_gemini_model(
    requested_model: str | None = None,
    *,
    cwd: Path | None = None,
) -> GeminiModelSelection:
    """Choose the best Gemini model using quota data and the preference chain."""
    chain = build_gemini_model_chain(requested_model)
    probe = await probe_gemini_quota(chain, cwd=cwd)
    return select_gemini_model_from_probe(chain, probe)


def infer_llm_provider(model: str) -> str:
    """Infer the LLM provider from a model name."""
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    if model.startswith("gemini"):
        return "google"
    return "google"


async def run_gemini_cli(
    prompt: str,
    *,
    model: str | None = None,
    cwd: Path | None = None,
    approval_mode: str = "yolo",
    output_format: str = "json",
    include_directories: list[str] | None = None,
    extra_args: list[str] | None = None,
) -> GeminiCLIResult:
    """Run Gemini CLI headlessly and parse its JSON wrapper output."""
    command = resolve_gemini_command()
    resolved_model = normalize_gemini_model(model)
    command.extend(["--model", resolved_model])
    if output_format:
        command.extend(["--output-format", output_format])
    if approval_mode:
        command.extend(["--approval-mode", approval_mode])
    if include_directories:
        command.extend(["--include-directories", ",".join(include_directories)])
    if extra_args:
        command.extend(extra_args)

    start = time.monotonic()
    environment = os.environ.copy()
    if not any(
        environment.get(name)
        for name in ("GOOGLE_GENAI_USE_GCA", "GOOGLE_GENAI_USE_VERTEXAI", "GEMINI_API_KEY")
    ):
        environment["GOOGLE_GENAI_USE_GCA"] = "true"
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd) if cwd is not None else None,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
    )
    stdout_bytes, stderr_bytes = await process.communicate(prompt.encode("utf-8"))
    duration_ms = int((time.monotonic() - start) * 1000)

    stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        raise RuntimeError(
            "Gemini CLI failed "
            f"(exit {process.returncode}). "
            f"stderr={stderr_text or '[empty]'} "
            f"stdout={stdout_text[:500] or '[empty]'}"
        )

    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini CLI returned non-JSON output. "
            f"stdout={stdout_text[:500] or '[empty]'} "
            f"stderr={stderr_text[:500] or '[empty]'}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            "Gemini CLI JSON output was not an object. "
            f"stdout={stdout_text[:500] or '[empty]'}"
        )

    if payload.get("error"):
        raise RuntimeError(
            f"Gemini CLI reported an error: {payload['error']!r}"
        )

    response = payload.get("response")
    if response is None:
        raise RuntimeError(
            "Gemini CLI JSON output did not contain a response field."
        )

    stats = payload.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {"value": stats}

    return GeminiCLIResult(
        response=str(response),
        stats=stats,
        raw=payload,
        duration_ms=duration_ms,
        command=tuple(command),
    )
