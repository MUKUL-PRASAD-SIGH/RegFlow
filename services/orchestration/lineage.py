"""Document lineage event logging to JSONL files."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LINEAGE_DIR = _REPO_ROOT / "data" / "lineage"


def _lineage_path(base_dir: Path | None = None) -> Path:
    return (base_dir or _DEFAULT_LINEAGE_DIR) / "events.jsonl"


def append_lineage_event(
    doc_id: str,
    stage: str,
    meta: dict[str, Any] | None = None,
    *,
    lineage_dir: Path | str | None = None,
) -> dict[str, Any]:
    """
    Append a lineage event for doc_id to data/lineage/events.jsonl.

    Returns the written event record.
    """
    directory = Path(lineage_dir) if lineage_dir else _DEFAULT_LINEAGE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "events.jsonl"

    event = {
        "doc_id": doc_id,
        "stage": stage,
        "meta": meta or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")) + "\n")

    return {"event": event, "path": str(path)}


def read_lineage_events(
    doc_id: str | None = None,
    *,
    lineage_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Read lineage events, optionally filtered by doc_id."""
    directory = Path(lineage_dir) if lineage_dir else _DEFAULT_LINEAGE_DIR
    path = directory / "events.jsonl"
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if doc_id is None or event.get("doc_id") == doc_id:
            events.append(event)
    return events
