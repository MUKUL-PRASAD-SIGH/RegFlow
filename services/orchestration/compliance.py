"""Worker-facing compliance / LLM job adapter."""

from __future__ import annotations

from typing import Any

from services.orchestration.compliance_jobs import run_compliance_analysis
from services.orchestration.lineage import append_lineage_event
from services.orchestration.metrics import MetricsStore


def process_compliance_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Process one Redis llm queue payload via deterministic compliance analysis."""
    result = run_compliance_analysis(payload)
    MetricsStore().increment("obligations_extracted", result.get("obligation_count", 0))
    doc_id = payload.get("doc_id") or payload.get("job_id") or "unknown"
    append_lineage_event(
        doc_id,
        "llm_output",
        {"obligation_count": result.get("obligation_count", 0), "mode": result.get("mode")},
    )
    return {**result, "job_id": payload.get("job_id")}


def process_llm_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Alias used by the LLM worker."""
    return process_compliance_job(payload)
