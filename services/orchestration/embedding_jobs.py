"""Embedding upsert jobs for Chroma vector store."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def upsert_embeddings(
    documents: list[dict[str, Any]],
    *,
    persist_dir: str | Path | None = None,
) -> dict[str, int]:
    """
    Upsert documents into RegulationVectorStore or a temporary Chroma path.

    Each document must include: id, content, domain, title, source, effective_date.
    Optional: keywords (list), embedding (list[float]).

    Returns counts: attempted, upserted, skipped.
    """
    if not documents:
        return {"attempted": 0, "upserted": 0, "skipped": 0}

    from services.knowledge.rag.vector_store import RegulationVectorStore

    target = str(persist_dir or Path.cwd() / "chroma_db")
    store = RegulationVectorStore(target)
    attempted = len(documents)
    valid = [d for d in documents if d.get("id") and d.get("content")]
    skipped = attempted - len(valid)

    if valid:
        store.upsert_documents(valid)

    return {"attempted": attempted, "upserted": len(valid), "skipped": skipped}


def upsert_to_temp_store(
    documents: list[dict[str, Any]],
    temp_dir: Path,
) -> dict[str, int]:
    """Upsert into an isolated temporary Chroma persist directory."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    return upsert_embeddings(documents, persist_dir=temp_dir)
