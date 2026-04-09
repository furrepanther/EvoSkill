"""Watchdog supervisor lifecycle logging for EvoSkill."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src.memory_fabric import get_shared_memfab_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WatchdogMemoryWriteResult:
    """Best-effort result from a Memory Fabric lifecycle write."""

    event_type: str
    status: str
    detail: str | None = None
    fingerprint_key: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_snapshot(
    *,
    load_1m: float | None = None,
    cpu_count: int | None = None,
    memory_available_mb: float | None = None,
    disk_free_gb: float | None = None,
) -> str:
    parts: list[str] = []
    if load_1m is not None and cpu_count is not None:
        parts.append(f"load={load_1m:.2f}/{cpu_count}")
    elif load_1m is not None:
        parts.append(f"load={load_1m:.2f}")
    if memory_available_mb is not None:
        parts.append(f"free_mem={memory_available_mb:.0f}MB")
    if disk_free_gb is not None:
        parts.append(f"disk_free={disk_free_gb:.2f}GB")
    return ", ".join(parts) if parts else "snapshot unavailable"


def _render_note(
    *,
    event_type: str,
    summary: str,
    what: str,
    why: str,
    impact: str,
    confidence: str,
    source_runner: str,
    source_tool: str,
    repo_or_system: str,
    component: str,
    category: str,
    evidence_refs: Sequence[str],
    tags: Sequence[str],
    when_to_apply: str,
    when_not_to_apply: str,
    observed_at_utc: str,
) -> str:
    lines = [
        f"event_type: {event_type}",
        f"summary: {summary}",
        f"what: {what}",
        f"why: {why}",
        f"impact: {impact}",
        f"confidence: {confidence}",
        f"source_runner: {source_runner}",
        f"source_tool: {source_tool}",
        f"repo_or_system: {repo_or_system}",
        f"component: {component}",
        f"category: {category}",
        f"observed_at_utc: {observed_at_utc}",
    ]
    if when_to_apply:
        lines.append(f"when_to_apply: {when_to_apply}")
    if when_not_to_apply:
        lines.append(f"when_not_to_apply: {when_not_to_apply}")
    if tags:
        lines.append(f"tags: {', '.join(tags)}")
    if evidence_refs:
        lines.append("evidence_refs:")
        lines.extend(f"- {ref}" for ref in evidence_refs)
    return "\n".join(lines).strip()


def _record_memory_store(
    event_type: str,
    *,
    summary: str,
    what: str,
    why: str,
    impact: str,
    confidence: str = "high",
    source_runner: str = "evoskill",
    source_tool: str = "watchdog_supervisor",
    repo_or_system: str = "EvoSkill",
    component: str = "scheduler",
    evidence_refs: Sequence[str] = (),
    tags: Sequence[str] = (),
    when_to_apply: str = "",
    when_not_to_apply: str = "",
    observed_at_utc: str | None = None,
    category: str = "watchdog_supervisor",
    client: Any | None = None,
) -> WatchdogMemoryWriteResult:
    resolved_client = client or get_shared_memfab_client()
    if resolved_client is None:
        logger.warning(
            "Memory Fabric client unavailable; could not record watchdog event %s",
            event_type,
        )
        return WatchdogMemoryWriteResult(
            event_type=event_type,
            status="unavailable",
            detail="Memory Fabric client unavailable",
        )

    observed = observed_at_utc or _utc_now()
    content = _render_note(
        event_type=event_type,
        summary=summary,
        what=what,
        why=why,
        impact=impact,
        confidence=confidence,
        source_runner=source_runner,
        source_tool=source_tool,
        repo_or_system=repo_or_system,
        component=component,
        category=category,
        evidence_refs=evidence_refs,
        tags=tags,
        when_to_apply=when_to_apply,
        when_not_to_apply=when_not_to_apply,
        observed_at_utc=observed,
    )
    try:
        response = resolved_client.call_tool(
            "memory_store",
            {
                "content": content,
                "source": source_tool,
                "scope": "global",
            },
        )
        payload = resolved_client.extract_tool_payload(response)
    except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
        logger.warning("Failed to record watchdog event %s: %s", event_type, exc)
        return WatchdogMemoryWriteResult(
            event_type=event_type,
            status="error",
            detail=str(exc),
        )

    status = "ok"
    detail = None
    fingerprint_key = None
    if isinstance(payload, dict):
        raw_status = str(payload.get("status") or "").strip().lower()
        if raw_status:
            status = raw_status
        raw_detail = payload.get("detail")
        if raw_detail not in (None, ""):
            detail = str(raw_detail)
        raw_fingerprint = payload.get("fingerprint_key")
        if raw_fingerprint not in (None, ""):
            fingerprint_key = str(raw_fingerprint)

    return WatchdogMemoryWriteResult(
        event_type=event_type,
        status=status,
        detail=detail,
        fingerprint_key=fingerprint_key,
        raw=payload if isinstance(payload, dict) else {"value": payload},
    )


def record_watchdog_supervisor_start(
    *,
    interval_hours: float,
    min_free_memory_mb: float,
    max_load_per_cpu: float,
    min_disk_free_gb: float,
    observed_at_utc: str | None = None,
    client: Any | None = None,
) -> WatchdogMemoryWriteResult:
    """Record that the supervisor has started."""
    return _record_memory_store(
        "watchdog_supervisor_start",
        summary=f"Watchdog supervisor started for scheduled EvoSkill runs every {interval_hours:g} hours",
        what=(
            "The scheduler entered its long-lived monitoring loop and will run "
            "EvoSkill twice-daily on a fixed cadence when resources are healthy. "
            f"Pressure gates: free_mem>={min_free_memory_mb:.0f}MB, "
            f"load_per_cpu<={max_load_per_cpu:g}, disk_free>={min_disk_free_gb:.0f}GB."
        ),
        why=(
            "Create a durable boot marker so operators can tell when the watchdog "
            "came up and which thresholds it was using."
        ),
        impact="Gives the next maintainer a clear starting point for lifecycle and failure analysis.",
        confidence="high",
        source_tool="watchdog_supervisor",
        component="schedule",
        category="implementation_note",
        tags=["watchdog", "scheduler", "start"],
        evidence_refs=[
            f"thresholds: free_mem>={min_free_memory_mb:.0f}MB, "
            f"load_per_cpu<={max_load_per_cpu:g}, disk_free>={min_disk_free_gb:.0f}GB"
        ],
        observed_at_utc=observed_at_utc,
        client=client,
        when_to_apply=(
            "Use when the EvoSkill scheduler boots and begins supervising twice-daily runs."
        ),
        when_not_to_apply="Do not use for individual run outcomes or resource-pressure skips.",
    )


def record_watchdog_supervisor_run_start(
    *,
    cycle: int,
    started_at_utc: str,
    next_run_utc: str,
    resource_snapshot: Any,
    observed_at_utc: str | None = None,
    client: Any | None = None,
) -> WatchdogMemoryWriteResult:
    """Record that a scheduled run attempt has started."""
    snapshot = _format_snapshot(
        load_1m=getattr(resource_snapshot, "load_1m", None),
        cpu_count=getattr(resource_snapshot, "cpu_count", None),
        memory_available_mb=getattr(resource_snapshot, "memory_available_mb", None),
        disk_free_gb=getattr(resource_snapshot, "disk_free_gb", None),
    )
    return _record_memory_store(
        "watchdog_supervisor_run_start",
        summary=f"Watchdog cycle {cycle} started",
        what=(
            f"Cycle {cycle} began at {started_at_utc} with {snapshot}; next scheduled window is {next_run_utc}."
        ),
        why=(
            "Persist the attempt boundary so a missing result can be recognized as a failure, not a silent gap."
        ),
        impact="Creates a durable start marker for each supervised run attempt.",
        confidence="high",
        source_tool="watchdog_supervisor",
        component="schedule",
        tags=["watchdog", "scheduler", "run", "start"],
        evidence_refs=[],
        observed_at_utc=observed_at_utc or started_at_utc,
        client=client,
    )


def record_watchdog_supervisor_run_result(
    *,
    cycle: int,
    status: str,
    started_at_utc: str,
    completed_at_utc: str,
    next_run_utc: str,
    resource_snapshot: Any,
    report: Any | None = None,
    pressure_reason: str | None = None,
    error: Exception | str | None = None,
    observed_at_utc: str | None = None,
    client: Any | None = None,
) -> WatchdogMemoryWriteResult:
    """Record the result of a scheduled run attempt."""
    snapshot = _format_snapshot(
        load_1m=getattr(resource_snapshot, "load_1m", None),
        cpu_count=getattr(resource_snapshot, "cpu_count", None),
        memory_available_mb=getattr(resource_snapshot, "memory_available_mb", None),
        disk_free_gb=getattr(resource_snapshot, "disk_free_gb", None),
    )
    evidence_refs: list[str] = []
    result_bits = [f"cycle={cycle}", f"status={status}", f"started={started_at_utc}", f"completed={completed_at_utc}"]
    if report is not None:
        run_id = getattr(report, "run_id", None)
        if run_id:
            result_bits.append(f"run_id={run_id}")
            project_root = getattr(report, "project_root", None)
            if project_root is not None:
                report_path = Path(project_root) / ".evoskill" / "reports" / f"run-{run_id}.md"
                telemetry_path = Path(project_root) / ".evoskill" / "telemetry" / f"run-{run_id}.json"
                evidence_refs.extend([str(report_path), str(telemetry_path)])
        baseline_score = getattr(report, "baseline_score", None)
        final_score = getattr(report, "final_score", None)
        if baseline_score is not None and final_score is not None:
            result_bits.append(f"baseline={baseline_score:.1%}")
            result_bits.append(f"final={final_score:.1%}")
        total_cost_usd = getattr(report, "total_cost_usd", None)
        if total_cost_usd is not None:
            result_bits.append(f"cost=${float(total_cost_usd):.4f}")
    if pressure_reason:
        result_bits.append(f"pressure={pressure_reason}")
    if error is not None:
        result_bits.append(f"error={error}")
    return _record_memory_store(
        "watchdog_supervisor_run_result",
        summary=f"Watchdog cycle {cycle} {status.replace('_', ' ')}",
        what=f"{snapshot}; " + "; ".join(result_bits) if result_bits else snapshot,
        why=(
            "Persist the outcome so operators can tell whether the cycle succeeded, skipped, or failed."
        ),
        impact="Creates the durable result marker for a scheduled run attempt.",
        confidence="high",
        source_tool="watchdog_supervisor",
        component="schedule",
        tags=["watchdog", "scheduler", "run", "result", status.replace("_", "-")],
        evidence_refs=evidence_refs,
        observed_at_utc=observed_at_utc or completed_at_utc,
        client=client,
    )


def record_watchdog_supervisor_stop(
    *,
    cycle: int,
    reason: str,
    observed_at_utc: str | None = None,
    client: Any | None = None,
) -> WatchdogMemoryWriteResult:
    """Record that the supervisor loop stopped."""
    return _record_memory_store(
        "watchdog_supervisor_stop",
        summary=f"Watchdog supervisor stopped after cycle {cycle}",
        what=f"The scheduler exited after {cycle} cycle(s) because {reason}.",
        why=(
            "Create a durable stop marker so future operators can see when the supervisor exited and why."
        ),
        impact="Makes the scheduler shutdown visible for incident review and restart checks.",
        confidence="high",
        source_tool="watchdog_supervisor",
        component="schedule",
        tags=["watchdog", "scheduler", "stop"],
        evidence_refs=[],
        observed_at_utc=observed_at_utc,
        client=client,
    )
