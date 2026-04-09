"""Memory Fabric retrieval helpers for EvoSkill."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_SHARED_SCRIPTS_ROOT = Path("/mnt/c/Users/furre/.gemini/antigravity/scripts")
_SHARED_MEMFAB_CLIENT_PATH = _SHARED_SCRIPTS_ROOT / "lib" / "memfab_mcp_client.py"
_SHARED_MEMFAB_CLIENT_MODULE_NAME = "_evoskill_shared_memfab_mcp_client"


@dataclass(frozen=True)
class MemoryFabricHit:
    """Normalized Memory Fabric retrieval hit."""

    title: str
    excerpt: str
    score: float | None = None
    source: str | None = None
    memory_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    tags: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class MemoryFabricRetrieval:
    """Structured result from a Memory Fabric retrieval query."""

    query: str
    hits: tuple[MemoryFabricHit, ...]
    status: str
    detail: str | None = None

    @property
    def hit_count(self) -> int:
        return len(self.hits)


def _truncate_text(text: str, limit: int) -> str:
    content = str(text or "").strip()
    if len(content) <= limit:
        return content
    if limit <= 12:
        return content[:limit]
    return content[: limit - 12].rstrip() + "…[truncated]"


def _pick_first(payload: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_tags(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return tuple(part for part in parts if part)
    return (str(value).strip(),)


def _flatten_payload_item(item: dict[str, Any]) -> dict[str, Any]:
    nested = item.get("memory")
    if isinstance(nested, dict):
        merged = dict(nested)
        merged.update({key: value for key, value in item.items() if key != "memory"})
        return merged
    return item


def _normalize_hit(item: dict[str, Any]) -> MemoryFabricHit:
    payload = _flatten_payload_item(item)
    title = str(
        _pick_first(
            payload,
            ("title", "name", "summary", "topic", "label", "memory_title"),
        )
        or "Memory hit"
    ).strip()
    excerpt_source = _pick_first(
        payload,
        ("excerpt", "summary", "content", "text", "body", "note", "description"),
    )
    if excerpt_source is None:
        excerpt_source = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    excerpt = _truncate_text(str(excerpt_source), 360)
    source = _pick_first(payload, ("source", "source_runner", "origin", "tool", "collection"))
    memory_id = _pick_first(payload, ("memory_id", "id", "uuid", "key"))
    created_at = _pick_first(payload, ("created_at", "created_at_utc", "timestamp", "observed_at_utc"))
    updated_at = _pick_first(payload, ("updated_at", "updated_at_utc"))
    score = _coerce_float(_pick_first(payload, ("score", "similarity", "confidence", "distance")))
    tags = _coerce_tags(_pick_first(payload, ("tags", "labels", "topics")))
    return MemoryFabricHit(
        title=title,
        excerpt=excerpt,
        score=score,
        source=str(source).strip() if source is not None else None,
        memory_id=str(memory_id).strip() if memory_id is not None else None,
        created_at=str(created_at).strip() if created_at is not None else None,
        updated_at=str(updated_at).strip() if updated_at is not None else None,
        tags=tags,
        raw=payload,
    )


def _normalize_hits(payload: dict[str, Any]) -> tuple[MemoryFabricHit, ...]:
    raw_hits = (
        payload.get("results")
        or payload.get("memories")
        or payload.get("final_shortlist")
        or payload.get("items")
        or []
    )
    hits: list[MemoryFabricHit] = []
    if isinstance(raw_hits, list):
        for item in raw_hits:
            if isinstance(item, dict):
                hits.append(_normalize_hit(item))
    return tuple(hits)


@lru_cache(maxsize=1)
def _load_shared_memfab_module() -> ModuleType | None:
    if not _SHARED_MEMFAB_CLIENT_PATH.exists():
        logger.info("Memory Fabric client helper not found at %s", _SHARED_MEMFAB_CLIENT_PATH)
        return None

    if str(_SHARED_SCRIPTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_SHARED_SCRIPTS_ROOT))

    spec = spec_from_file_location(_SHARED_MEMFAB_CLIENT_MODULE_NAME, _SHARED_MEMFAB_CLIENT_PATH)
    if spec is None or spec.loader is None:
        logger.warning("Unable to load Memory Fabric client helper from %s", _SHARED_MEMFAB_CLIENT_PATH)
        return None

    module = module_from_spec(spec)
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    except (ImportError, ModuleNotFoundError, FileNotFoundError, OSError, SyntaxError, AttributeError, ValueError) as exc:
        sys.modules.pop(spec.name, None)
        logger.warning("Failed to import Memory Fabric client helper: %s", exc)
        return None
    return module


def get_shared_memfab_client() -> Any | None:
    """Return the shared Memfab client if the shared helper is available."""
    module = _load_shared_memfab_module()
    if module is None:
        return None

    client_cls = getattr(module, "MemfabMCPClient", None)
    if client_cls is None or not getattr(client_cls, "is_configured", lambda: False)():
        logger.info("Memory Fabric client is not configured for this environment.")
        return None

    shared_client_factory = getattr(module, "get_shared_memfab_client", None)
    if callable(shared_client_factory):
        try:
            return shared_client_factory()
        except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:  # pragma: no cover - external integration guard
            logger.warning("Memory Fabric shared client unavailable: %s", exc)
            return None

    try:
        return client_cls()
    except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:  # pragma: no cover - external integration guard
        logger.warning("Memory Fabric client creation failed: %s", exc)
        return None


def retrieve_memory_fabric_context(
    query: str,
    *,
    top_k: int = 6,
    client: Any | None = None,
) -> MemoryFabricRetrieval:
    """Run `memory_retrieve` and normalize the returned memories."""
    normalized_query = query.strip()
    if not normalized_query:
        return MemoryFabricRetrieval(
            query="",
            hits=(),
            status="empty",
            detail="Empty Memory Fabric query",
        )

    resolved_client = client or get_shared_memfab_client()
    if resolved_client is None:
        return MemoryFabricRetrieval(
            query=normalized_query,
            hits=(),
            status="unavailable",
            detail="Memory Fabric client unavailable",
        )

    try:
        response = resolved_client.call_tool(
            "memory_retrieve",
            {"query": normalized_query, "top_k": top_k},
        )
        payload = resolved_client.extract_tool_payload(response)
    except (RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:  # pragma: no cover - external integration guard
        logger.warning("Memory Fabric retrieval failed: %s", exc)
        return MemoryFabricRetrieval(
            query=normalized_query,
            hits=(),
            status="error",
            detail=str(exc),
        )

    hits = _normalize_hits(payload if isinstance(payload, dict) else {})
    if not hits:
        return MemoryFabricRetrieval(
            query=normalized_query,
            hits=(),
            status="empty",
            detail="Memory Fabric returned no relevant hits",
        )

    return MemoryFabricRetrieval(
        query=normalized_query,
        hits=hits,
        status="ok",
    )


def render_memory_fabric_context(retrieval: MemoryFabricRetrieval) -> str:
    """Render a compact prompt section for retrieved Memory Fabric hits."""
    lines = ["## Memory Fabric Context"]
    if retrieval.query:
        lines.append(f"- Query: {_truncate_text(retrieval.query, 220)}")

    if retrieval.status != "ok" or not retrieval.hits:
        detail = retrieval.detail or "No relevant Memory Fabric hits returned."
        lines.append(f"- {detail}")
        return "\n".join(lines)

    for index, hit in enumerate(retrieval.hits, start=1):
        meta_parts = []
        if hit.score is not None:
            meta_parts.append(f"score={hit.score:.3f}")
        if hit.source:
            meta_parts.append(f"source={hit.source}")
        if hit.memory_id:
            meta_parts.append(f"id={hit.memory_id}")
        if hit.tags:
            meta_parts.append(f"tags={', '.join(hit.tags[:4])}")
        meta = f" ({'; '.join(meta_parts)})" if meta_parts else ""
        lines.append(f"{index}. {hit.title}{meta}")
        lines.append(f"   - {_truncate_text(hit.excerpt, 320)}")

    return "\n".join(lines)
