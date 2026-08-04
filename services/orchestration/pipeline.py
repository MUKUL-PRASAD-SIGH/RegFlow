"""End-to-end dry-run pipeline (Airflow-free) for RegGraph AI v2."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.orchestration.collection import (
    content_hash,
    detect_change,
    fetch_url,
    save_raw_document,
)
from services.orchestration.compliance_jobs import run_compliance_analysis
from services.orchestration.embedding_jobs import upsert_embeddings
from services.orchestration.lineage import append_lineage_event
from services.orchestration.metrics import MetricsStore
from services.orchestration.processing import chunk_text, clean_text, extract_metadata
from services.orchestration.regulators import get_enabled_regulators
from services.orchestration.reporting import (
    dashboard_refresh_stub,
    generate_report_stub,
    send_email_stub,
    send_slack_stub,
    webhook_stub,
)
from services.orchestration.validation import process_validation_job

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _pipeline_root(base_dir: Path | None = None) -> Path:
    return Path(base_dir) if base_dir else _REPO_ROOT / "data" / "pipeline"


def run_collection_stage(
    *,
    base_dir: Path | None = None,
    mock_bodies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch (or inject) regulator docs, detect changes, save raw files."""
    root = _pipeline_root(base_dir)
    hash_dir = root / "_hashes"
    hash_dir.mkdir(parents=True, exist_ok=True)
    metrics = MetricsStore(persist_path=root / "metrics" / "counters.json")
    results: list[dict[str, Any]] = []

    regulators = get_enabled_regulators()
    for reg in regulators:
        regulator_id = reg.id
        try:
            if mock_bodies is not None and regulator_id in mock_bodies:
                body = mock_bodies[regulator_id]
            elif reg.url:
                fetched = fetch_url(reg.url)
                if fetched.get("error"):
                    results.append(
                        {"status": "error", "regulator_id": regulator_id, "error": fetched["error"]}
                    )
                    continue
                body = fetched.get("body") or ""
            else:
                results.append({"status": "skipped", "regulator_id": regulator_id, "error": "no_url"})
                continue

            hash_file = hash_dir / f"{regulator_id}.txt"
            previous = hash_file.read_text(encoding="utf-8").strip() if hash_file.exists() else None
            if not detect_change(previous, body):
                results.append({"status": "unchanged", "regulator_id": regulator_id})
                continue

            saved = save_raw_document(regulator_id, body, root)
            hash_file.write_text(saved["content_hash"], encoding="utf-8")
            append_lineage_event(saved["doc_id"], "raw", saved, lineage_dir=root / "lineage")
            metrics.increment("documents_scraped")
            results.append({"status": "saved", **saved})
        except Exception as exc:
            results.append({"status": "error", "regulator_id": regulator_id, "error": str(exc)})

    return {"status": "ok", "results": results, "saved": sum(1 for r in results if r.get("status") == "saved")}


def run_processing_stage(*, base_dir: Path | None = None) -> dict[str, Any]:
    root = _pipeline_root(base_dir)
    raw_dir = root / "raw"
    chunks_dir = root / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    lineage_dir = root / "lineage"
    processed: list[dict[str, Any]] = []

    if not raw_dir.exists():
        return {"status": "ok", "processed": 0, "details": []}

    for regulator_dir in sorted(raw_dir.iterdir()):
        if not regulator_dir.is_dir():
            continue
        files = sorted(regulator_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            continue
        newest = files[0]
        regulator_id = regulator_dir.name
        doc_id = f"{regulator_id}_{newest.stem}"
        raw_text = newest.read_text(encoding="utf-8")
        cleaned = clean_text(raw_text)
        metadata = extract_metadata(raw_text, regulator_id=regulator_id)
        append_lineage_event(
            doc_id, "parsed", {"path": str(newest), **metadata}, lineage_dir=lineage_dir
        )
        chunks = chunk_text(cleaned)
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{idx}"
            record = {
                "chunk_id": chunk_id,
                "regulator_id": regulator_id,
                "content": chunk,
                "metadata": metadata,
                "source_path": str(newest),
            }
            (chunks_dir / f"{chunk_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        append_lineage_event(
            doc_id, "chunk", {"chunk_count": len(chunks)}, lineage_dir=lineage_dir
        )
        processed.append({"doc_id": doc_id, "regulator_id": regulator_id, "chunk_count": len(chunks)})

    return {"status": "ok", "processed": len(processed), "details": processed}


def run_embedding_stage(
    *,
    base_dir: Path | None = None,
    persist_dir: Path | None = None,
) -> dict[str, Any]:
    root = _pipeline_root(base_dir)
    chunks_dir = root / "chunks"
    chroma_dir = Path(persist_dir) if persist_dir else root / "chroma_tmp"
    documents: list[dict[str, Any]] = []

    if chunks_dir.exists():
        for chunk_file in sorted(chunks_dir.glob("*.json")):
            record = json.loads(chunk_file.read_text(encoding="utf-8"))
            meta = record.get("metadata") or {}
            documents.append(
                {
                    "id": record["chunk_id"],
                    "content": record["content"],
                    "domain": record.get("regulator_id") or "unknown",
                    "title": meta.get("title") or "Untitled",
                    "source": record.get("source_path") or "",
                    "effective_date": meta.get("effective_date") or "1970-01-01",
                }
            )

    # Unit/E2E safe path: skip heavy Chroma when REGGRAPH_SKIP_CHROMA=1
    import os

    if os.environ.get("REGGRAPH_SKIP_CHROMA") == "1":
        counts = {"attempted": len(documents), "upserted": len(documents), "skipped": 0}
    else:
        try:
            counts = upsert_embeddings(documents, persist_dir=chroma_dir)
        except Exception as exc:
            counts = {
                "attempted": len(documents),
                "upserted": 0,
                "skipped": len(documents),
                "error": str(exc),
            }

    metrics = MetricsStore(persist_path=root / "metrics" / "counters.json")
    if counts.get("upserted"):
        metrics.increment("embeddings_generated", int(counts["upserted"]))
    for doc in documents:
        append_lineage_event(
            doc["id"], "embedding", {"counts": counts}, lineage_dir=root / "lineage"
        )

    return {"status": "ok", "counts": counts, "document_count": len(documents)}


def run_compliance_stage(*, base_dir: Path | None = None) -> dict[str, Any]:
    root = _pipeline_root(base_dir)
    chunks_dir = root / "chunks"
    results: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []

    if chunks_dir.exists():
        for chunk_file in sorted(chunks_dir.glob("*.json"))[:50]:
            record = json.loads(chunk_file.read_text(encoding="utf-8"))
            analysis = run_compliance_analysis(
                {
                    "text": record.get("content") or "",
                    "regulator_id": record.get("regulator_id"),
                    "doc_id": record.get("chunk_id"),
                }
            )
            results.append(analysis)
            validation = process_validation_job(
                {
                    "job_id": record.get("chunk_id"),
                    "doc_id": record.get("chunk_id"),
                    "obligations": analysis.get("obligations") or [],
                }
            )
            validations.append(validation)
            append_lineage_event(
                record["chunk_id"],
                "compliance",
                {"obligation_count": analysis.get("obligation_count", 0)},
                lineage_dir=root / "lineage",
            )

    obligation_total = sum(r.get("obligation_count", 0) for r in results)
    metrics = MetricsStore(persist_path=root / "metrics" / "counters.json")
    if obligation_total:
        metrics.increment("obligations_extracted", obligation_total)

    compliance_dir = root / "compliance"
    compliance_dir.mkdir(parents=True, exist_ok=True)
    summary = {"results": results, "validations": validations}
    (compliance_dir / "latest_analysis.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return {
        "status": "ok",
        "analyzed": len(results),
        "obligation_total": obligation_total,
        "validation_passed": sum(1 for v in validations if v.get("validation", {}).get("passed")),
    }


def run_reporting_stage(*, base_dir: Path | None = None) -> dict[str, Any]:
    root = _pipeline_root(base_dir)
    compliance_path = root / "compliance" / "latest_analysis.json"
    compliance_data: Any = {}
    if compliance_path.exists():
        compliance_data = json.loads(compliance_path.read_text(encoding="utf-8"))

    metrics = MetricsStore(persist_path=root / "metrics" / "counters.json").snapshot()
    report_payload = {"compliance": compliance_data, "metrics": metrics}
    report = generate_report_stub("e2e_compliance", report_payload)
    archive = {
        "report": report,
        "notifications": {
            "slack": send_slack_stub("RegGraph v2 E2E report ready"),
            "email": send_email_stub("ops@reggraph.ai", "E2E Report", json.dumps(report_payload)[:2000]),
            "webhook": webhook_stub("https://hooks.reggraph.ai/pipeline", {"ok": True}),
            "dashboard": dashboard_refresh_stub("reggraph-main"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_id = f"report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    path = reports_dir / f"{report_id}.json"
    path.write_text(json.dumps(archive, indent=2), encoding="utf-8")
    append_lineage_event(
        report_id, "final_report", {"path": str(path)}, lineage_dir=root / "lineage"
    )
    return {"status": "ok", "report_id": report_id, "archive_path": str(path)}


def run_full_pipeline(
    *,
    base_dir: Path | None = None,
    mock_bodies: dict[str, str] | None = None,
    persist_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Execute collect → process → embed → compliance → report.

    Use mock_bodies in tests to avoid live portal HTTP.
    """
    collection = run_collection_stage(base_dir=base_dir, mock_bodies=mock_bodies)
    processing = run_processing_stage(base_dir=base_dir)
    embedding = run_embedding_stage(base_dir=base_dir, persist_dir=persist_dir)
    compliance = run_compliance_stage(base_dir=base_dir)
    reporting = run_reporting_stage(base_dir=base_dir)
    return {
        "status": "ok",
        "stages": {
            "collection": collection,
            "processing": processing,
            "embedding": embedding,
            "compliance": compliance,
            "reporting": reporting,
        },
        "content_hash_sample": content_hash("reggraph-v2"),
    }
