"""Tests for worker-facing orchestration adapters."""

from __future__ import annotations

from pathlib import Path


def test_process_embedding_job_from_content(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from services.orchestration.embedding import process_embedding_job

    # Avoid heavy chromadb in unit test — stub upsert
    monkeypatch.setattr(
        "services.orchestration.embedding.upsert_embeddings",
        lambda documents, persist_dir=None: {"attempted": 1, "upserted": 1, "skipped": 0},
    )
    monkeypatch.setattr(
        "services.orchestration.embedding.append_lineage_event",
        lambda *a, **k: {"ok": True},
    )

    result = process_embedding_job(
        {
            "job_id": "j1",
            "doc_id": "d1",
            "content": "Entities shall file GST returns monthly.",
            "regulator_id": "gstn",
        }
    )
    assert result["status"] == "ok"
    assert result["counts"]["upserted"] == 1


def test_process_compliance_and_validation():
    from services.orchestration.compliance import process_llm_job
    from services.orchestration.validation import process_validation_job

    analysis = process_llm_job(
        {
            "job_id": "j2",
            "doc_id": "d2",
            "text": "Taxpayers must submit Form GSTR-3B before the due date.",
            "regulator_id": "gstn",
        }
    )
    assert analysis["status"] == "ok"
    assert analysis["obligation_count"] >= 1

    validation = process_validation_job(
        {
            "job_id": "j2",
            "doc_id": "d2",
            "obligations": analysis["obligations"],
        }
    )
    assert validation["validation"]["passed"] is True
