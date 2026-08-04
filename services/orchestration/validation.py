"""Worker-facing rule validation job adapter."""

from __future__ import annotations

from typing import Any

from services.orchestration.lineage import append_lineage_event
from services.orchestration.metrics import MetricsStore


def process_validation_job(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministic validation of extracted obligations.

    Flags empty obligations and conflicting severity labels as rule conflicts.
    """
    obligations = payload.get("obligations") or []
    errors: list[str] = []
    conflicts = 0

    if not obligations:
        errors.append("no_obligations")

    for obl in obligations:
        text = (obl.get("text") or "").strip()
        if len(text) < 10:
            errors.append(f"short_obligation:{obl.get('id')}")
        severity = (obl.get("severity") or "").lower()
        if severity not in {"low", "medium", "high", "critical"}:
            conflicts += 1
            errors.append(f"invalid_severity:{obl.get('id')}")

    metrics = MetricsStore()
    if errors:
        metrics.increment("rule_conflicts", max(conflicts, 1))
    if payload.get("force_failure"):
        metrics.increment("agent_failures", 1)
        errors.append("forced_failure")

    passed = len(errors) == 0
    doc_id = payload.get("doc_id") or payload.get("job_id") or "unknown"
    append_lineage_event(
        doc_id,
        "rule_validation",
        {"passed": passed, "errors": errors, "obligation_count": len(obligations)},
    )

    return {
        "status": "ok" if passed else "failed",
        "job_id": payload.get("job_id"),
        "validation": {"passed": passed, "errors": errors},
        "doc_id": doc_id,
    }
