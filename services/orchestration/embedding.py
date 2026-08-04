"""Worker-facing embedding job adapter."""

from __future__ import annotations

from typing import Any

from services.orchestration.embedding_jobs import upsert_embeddings
from services.orchestration.lineage import append_lineage_event
from services.orchestration.metrics import MetricsStore


def process_embedding_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Process one Redis embed queue payload."""
    documents = payload.get("documents") or []
    if not documents and payload.get("content"):
        documents = [
            {
                "id": payload.get("doc_id") or payload.get("job_id") or "doc-1",
                "content": payload["content"],
                "domain": payload.get("domain") or payload.get("regulator_id") or "general",
                "title": payload.get("title") or "Regulatory document",
                "source": payload.get("source") or payload.get("regulator_id") or "unknown",
                "effective_date": payload.get("effective_date") or "1970-01-01",
                "keywords": payload.get("keywords") or [],
            }
        ]

    persist_dir = payload.get("persist_dir")
    counts = upsert_embeddings(documents, persist_dir=persist_dir)
    MetricsStore().increment("embeddings_generated", counts.get("upserted", 0))

    doc_id = payload.get("doc_id") or (documents[0]["id"] if documents else "unknown")
    append_lineage_event(doc_id, "embedding", {"counts": counts, "job_id": payload.get("job_id")})

    return {"status": "ok", "counts": counts, "job_id": payload.get("job_id"), "doc_id": doc_id}
