"""Structured run telemetry for EvoSkill.

This module keeps the telemetry schema separate from the loop logic so the
run loop can emit compact, machine-usable events while the CLI persists a
single durable run artifact at the end of execution.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.agent_profiles.base import AgentTrace


def make_run_id(now: datetime | None = None) -> str:
    """Return a stable, filename-safe run identifier."""
    moment = now or datetime.now(timezone.utc)
    return moment.strftime("%Y-%m-%d-%H%M%S-%f")


def _truncate(text: str, limit: int) -> str:
    content = str(text or "").strip()
    if len(content) <= limit:
        return content
    if limit <= 12:
        return content[:limit]
    return content[: limit - 12].rstrip() + "…[truncated]"


class TelemetryTraceSnapshot(BaseModel):
    """Compact, JSON-safe view of an AgentTrace."""

    uuid: str
    session_id: str
    model: str
    tools: list[str]
    duration_ms: int
    total_cost_usd: float
    num_turns: int
    usage: dict[str, Any]
    result_excerpt: str
    is_error: bool
    structured_output_repaired: bool = False
    parse_error: str | None = None
    output: Any = None


def trace_to_snapshot(trace: AgentTrace[Any], *, result_chars: int = 1_200) -> TelemetryTraceSnapshot:
    """Convert a full AgentTrace into a compact telemetry snapshot."""
    output_payload = None
    if trace.output is not None:
        if hasattr(trace.output, "model_dump"):
            output_payload = trace.output.model_dump()
        else:
            output_payload = trace.output

    return TelemetryTraceSnapshot(
        uuid=trace.uuid,
        session_id=trace.session_id,
        model=trace.model,
        tools=list(trace.tools),
        duration_ms=trace.duration_ms,
        total_cost_usd=trace.total_cost_usd,
        num_turns=trace.num_turns,
        usage=dict(trace.usage),
        result_excerpt=_truncate(trace.result, result_chars),
        is_error=trace.is_error,
        structured_output_repaired=trace.structured_output_repaired,
        parse_error=trace.parse_error,
        output=output_payload,
    )


class TelemetryEvent(BaseModel):
    """Normalized loop event."""

    kind: str
    at_utc: str
    iteration: int | None = None
    total: int | None = None
    iterations: int | None = None
    parent: str | None = None
    child_name: str | None = None
    category: str | None = None
    question: str | None = None
    agent_answer: str | None = None
    ground_truth: str | None = None
    score: float | None = None
    passed: bool | None = None
    n_skills: int | None = None
    status: str | None = None
    action: str | None = None
    target_skill: str | None = None
    proposal: str | None = None
    justification: str | None = None
    parent_score: float | None = None
    added: bool | None = None
    best: str | None = None
    best_score: float | None = None
    frontier: list[dict[str, Any]] = Field(default_factory=list)
    trace: TelemetryTraceSnapshot | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RunTelemetry(BaseModel):
    """Durable structured record for a single EvoSkill run."""

    schema_version: str = "1.0"
    run_id: str
    created_at_utc: str
    updated_at_utc: str
    project_root: str
    task_name: str
    task_description: str = ""
    task_constraints: str = ""
    dataset_path: str
    harness: str
    model: str | None = None
    evolution_mode: str
    iterations_requested: int
    frontier_size: int
    concurrency: int
    failure_samples: int
    train_ratio: float
    val_ratio: float
    baseline_score: float | None = None
    final_score: float | None = None
    best_program: str | None = None
    iterations_completed: int | None = None
    total_cost_usd: float = 0.0
    source_map: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    events: list[TelemetryEvent] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        run_id: str | None = None,
        project_root: Path,
        task_name: str,
        task_description: str,
        task_constraints: str,
        dataset_path: Path,
        harness: str,
        model: str | None,
        evolution_mode: str,
        iterations_requested: int,
        frontier_size: int,
        concurrency: int,
        failure_samples: int,
        train_ratio: float,
        val_ratio: float,
        dataset_summary: dict[str, Any] | None = None,
    ) -> "RunTelemetry":
        moment = datetime.now(timezone.utc)
        telemetry = cls(
            run_id=run_id or make_run_id(moment),
            created_at_utc=moment.isoformat(),
            updated_at_utc=moment.isoformat(),
            project_root=str(project_root),
            task_name=task_name,
            task_description=task_description,
            task_constraints=task_constraints,
            dataset_path=str(dataset_path),
            harness=harness,
            model=model,
            evolution_mode=evolution_mode,
            iterations_requested=iterations_requested,
            frontier_size=frontier_size,
            concurrency=concurrency,
            failure_samples=failure_samples,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            dataset_summary=dataset_summary or {},
        )
        telemetry.source_map = {
            "sample_traces": "SelfImprovingLoop._evaluate -> AgentTrace",
            "validation_traces": "SelfImprovingLoop._evaluate -> AgentTrace",
            "memory_context": "src.memory_fabric.retrieve_memory_fabric_context",
            "failure_briefs": "src.loop.helpers.build_proposer_query",
            "feedback_history": ".claude/feedback_history.md",
            "frontier_state": "src.registry.ProgramManager git branches/tags",
            "run_summary": "src.cli.report.RunReport",
            "console_events": "LoopDisplay.on_event",
        }
        return telemetry

    def _touch(self) -> None:
        self.updated_at_utc = datetime.now(timezone.utc).isoformat()

    @classmethod
    def load(cls, path: Path) -> "RunTelemetry":
        """Load a telemetry bundle from disk."""
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def add_event(self, kind: str, **payload: Any) -> TelemetryEvent:
        payload = dict(payload)
        if kind == "proposal" and "summary" in payload and "proposal" not in payload:
            payload["proposal"] = payload.pop("summary")
        if kind == "skill_written":
            if "name" in payload and "child_name" not in payload:
                payload["child_name"] = payload.pop("name")
            if "target" in payload and "target_skill" not in payload:
                payload["target_skill"] = payload.pop("target")

        trace_payload = payload.pop("trace", None)
        frontier_payload = payload.pop("frontier", None)

        if trace_payload is not None and isinstance(trace_payload, AgentTrace):
            trace_payload = trace_to_snapshot(trace_payload)
        elif trace_payload is not None and isinstance(trace_payload, dict):
            trace_payload = TelemetryTraceSnapshot.model_validate(trace_payload)

        normalized_frontier: list[dict[str, Any]] = []
        if frontier_payload:
            for item in frontier_payload:
                if isinstance(item, dict):
                    normalized_frontier.append(
                        {
                            "name": str(item.get("name", "")),
                            "score": item.get("score"),
                        }
                    )
                else:
                    name, score = item
                    normalized_frontier.append({"name": name, "score": score})

        known_fields = set(TelemetryEvent.model_fields)
        event_payload: dict[str, Any] = {}
        extra_payload: dict[str, Any] = {}
        for key, value in payload.items():
            if key in known_fields and key != "extra":
                event_payload[key] = value
            else:
                extra_payload[key] = value
        if extra_payload:
            existing_extra = event_payload.get("extra")
            if isinstance(existing_extra, dict):
                existing_extra.update(extra_payload)
            else:
                event_payload["extra"] = extra_payload

        event = TelemetryEvent(
            kind=kind,
            at_utc=datetime.now(timezone.utc).isoformat(),
            trace=trace_payload,
            frontier=normalized_frontier,
            **event_payload,
        )
        self.events.append(event)
        self._touch()
        return event

    def finalize(
        self,
        *,
        baseline_score: float | None,
        final_score: float | None,
        best_program: str | None,
        iterations_completed: int | None,
        total_cost_usd: float,
    ) -> None:
        self.baseline_score = baseline_score
        self.final_score = final_score
        self.best_program = best_program
        self.iterations_completed = iterations_completed
        self.total_cost_usd = total_cost_usd
        self._touch()

    def attach_artifact(self, name: str, path: Path | str) -> None:
        self.artifacts[name] = str(path)
        self._touch()

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return path
