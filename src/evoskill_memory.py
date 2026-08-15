"""Memory Fabric publishing helpers for EvoSkill run outcomes."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src.memory_fabric import get_shared_memfab_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvoSkillMemoryWriteResult:
    """Best-effort result from a Memory Fabric EvoSkill write."""

    record_type: str
    status: str
    detail: str | None = None
    fingerprint_key: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _truncate_text(text: str, limit: int) -> str:
    content = str(text or "").strip()
    if len(content) <= limit:
        return content
    if limit <= 12:
        return content[:limit]
    return content[: limit - 12].rstrip() + "…[truncated]"


def _render_note(
    *,
    record_type: str,
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
    observed_at_utc: str,
    family: str,
    when_to_apply: str = "",
    when_not_to_apply: str = "",
) -> str:
    lines = [
        f"record_type: {record_type}",
        f"summary: {summary}",
        f"family: {family}",
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
    record_type: str,
    *,
    summary: str,
    what: str,
    why: str,
    impact: str,
    confidence: str = "high",
    source_runner: str = "evoskill",
    source_tool: str = "evoskill_run",
    repo_or_system: str = "EvoSkill",
    component: str = "family",
    category: str = "run_outcome",
    evidence_refs: Sequence[str] = (),
    tags: Sequence[str] = (),
    when_to_apply: str = "",
    when_not_to_apply: str = "",
    observed_at_utc: str | None = None,
    family: str = "evoskill_run",
    client: Any | None = None,
) -> EvoSkillMemoryWriteResult:
    resolved_client = client or get_shared_memfab_client()
    if resolved_client is None:
        logger.warning(
            "Memory Fabric client unavailable; could not record EvoSkill event %s",
            record_type,
        )
        return EvoSkillMemoryWriteResult(
            record_type=record_type,
            status="unavailable",
            detail="Memory Fabric client unavailable",
        )

    observed = observed_at_utc or _utc_now()
    content = _render_note(
        record_type=record_type,
        summary=summary,
        family=family,
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
        observed_at_utc=observed,
        when_to_apply=when_to_apply,
        when_not_to_apply=when_not_to_apply,
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
        logger.warning("Failed to record EvoSkill event %s: %s", record_type, exc)
        return EvoSkillMemoryWriteResult(
            record_type=record_type,
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

    return EvoSkillMemoryWriteResult(
        record_type=record_type,
        status=status,
        detail=detail,
        fingerprint_key=fingerprint_key,
        raw=payload if isinstance(payload, dict) else {"value": payload},
    )


def _format_score_delta(score_delta: float) -> str:
    sign = "+" if score_delta >= 0 else ""
    return f"{sign}{score_delta:.1%}"


def record_evoskill_family_outcome(
    *,
    run_id: str,
    project_root: Path,
    best_program: str,
    baseline_score: float,
    final_score: float,
    iterations_completed: int,
    total_cost_usd: float,
    report_path: Path | None = None,
    telemetry_path: Path | None = None,
    observed_at_utc: str | None = None,
    client: Any | None = None,
) -> EvoSkillMemoryWriteResult:
    """Record the family-level EvoSkill run outcome in Memory Fabric."""
    improvement = final_score - baseline_score
    evidence_refs = [str(path) for path in (report_path, telemetry_path) if path is not None]
    return _record_memory_store(
        "evoskill_family_complete",
        summary=f"EvoSkill run {run_id} completed",
        what=(
            f"family=evoskill_run; run_id={run_id}; best_program={best_program}; "
            f"baseline={baseline_score:.1%}; final={final_score:.1%}; "
            f"improvement={improvement:+.1%}; iterations={iterations_completed}; "
            f"cost=${total_cost_usd:.4f}; project_root={project_root}"
        ),
        why=(
            "Persist the family-level outcome so later retrieval can recover the run lineage "
            "without reconstructing it from git branches alone."
        ),
        impact=(
            "Lets Memory Fabric retrieve the EvoSkill run family, the best program, and the "
            "overall effect of the run in one place."
        ),
        source_tool="evoskill_run",
        component="family",
        category="run_outcome",
        tags=["evoskill", "family", "run", "complete", best_program],
        evidence_refs=evidence_refs,
        observed_at_utc=observed_at_utc,
        family="evoskill_run",
        when_to_apply="Use after a completed EvoSkill run, even when no skills were kept.",
        when_not_to_apply="Do not use for individual iteration events.",
        client=client,
    )


def record_evoskill_skill_outcome(
    *,
    run_id: str,
    project_root: Path,
    skill_name: str,
    iteration: int,
    score_delta: float,
    action: str,
    best_program: str,
    report_path: Path | None = None,
    telemetry_path: Path | None = None,
    observed_at_utc: str | None = None,
    client: Any | None = None,
) -> EvoSkillMemoryWriteResult:
    """Record an affected EvoSkill skill in Memory Fabric."""
    skill_path = project_root / ".claude" / "skills" / skill_name / "SKILL.md"
    evidence_refs = [str(path) for path in (skill_path, report_path, telemetry_path) if path is not None]
    action_label = "edited" if action == "edit" else "created"
    return _record_memory_store(
        "evoskill_skill_complete",
        summary=f"EvoSkill {action_label} skill {skill_name}",
        what=(
            f"family=evoskill_run; run_id={run_id}; skill_name={skill_name}; "
            f"action={action}; iteration={iteration}; score_delta={_format_score_delta(score_delta)}; "
            f"best_program={best_program}; skill_path={skill_path}"
        ),
        why=(
            "Persist the affected skill directly so later retrieval can target the skill-level change "
            "instead of the whole run."
        ),
        impact=(
            "Improves retrieval for future proposer runs, skill maintenance, and postmortem analysis."
        ),
        source_tool="evoskill_run",
        component="skill",
        category="skill_update",
        tags=["evoskill", "skill", action, "kept", skill_name],
        evidence_refs=evidence_refs,
        observed_at_utc=observed_at_utc,
        family="evoskill_run",
        when_to_apply="Use after EvoSkill keeps a skill on the frontier.",
        when_not_to_apply="Do not use for discarded or provisional skills.",
        client=client,
    )


def publish_evoskill_run_memory(
    *,
    run_id: str,
    project_root: Path,
    best_program: str,
    baseline_score: float,
    final_score: float,
    iterations_completed: int,
    total_cost_usd: float,
    skills_kept: Sequence[Any],
    report_path: Path | None = None,
    telemetry_path: Path | None = None,
    client: Any | None = None,
) -> list[EvoSkillMemoryWriteResult]:
    """Publish the family-level outcome and kept skills for a completed EvoSkill run."""
    results = [
        record_evoskill_family_outcome(
            run_id=run_id,
            project_root=project_root,
            best_program=best_program,
            baseline_score=baseline_score,
            final_score=final_score,
            iterations_completed=iterations_completed,
            total_cost_usd=total_cost_usd,
            report_path=report_path,
            telemetry_path=telemetry_path,
            client=client,
        )
    ]

    for skill in skills_kept:
        skill_name = _get_value(skill, "name")
        if not skill_name:
            continue
        iteration = int(_get_value(skill, "iteration", 0) or 0)
        score_delta = float(_get_value(skill, "score_delta", 0.0) or 0.0)
        action = str(_get_value(skill, "action", "create") or "create")
        results.append(
            record_evoskill_skill_outcome(
                run_id=run_id,
                project_root=project_root,
                skill_name=str(skill_name),
                iteration=iteration,
                score_delta=score_delta,
                action=action,
                best_program=best_program,
                report_path=report_path,
                telemetry_path=telemetry_path,
                client=client,
            )
        )

    return results
