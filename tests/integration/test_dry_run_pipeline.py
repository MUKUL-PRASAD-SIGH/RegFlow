"""Dry-run pipeline without Airflow — collection → process → compliance → validate → report."""

from __future__ import annotations

from pathlib import Path

from services.orchestration.collection import content_hash, detect_change, save_raw_document
from services.orchestration.compliance_jobs import run_compliance_analysis
from services.orchestration.lineage import append_lineage_event, read_lineage_events
from services.orchestration.processing import chunk_text, clean_text
from services.orchestration.reporting import (
    dashboard_refresh_stub,
    generate_report_stub,
    send_email_stub,
    send_slack_stub,
)
from services.orchestration.validation import process_validation_job


def test_dry_run_pipeline_stages(tmp_path: Path):
    lineage_dir = tmp_path / "lineage"
    body = (
        "Circular: Registered persons must file GSTR-3B on or before the due date. "
        "Employers shall deposit provident fund contributions by the 15th of each month."
    )
    assert detect_change(None, body) is True
    digest = content_hash(body)

    saved = save_raw_document("gstn", body, tmp_path / "pipeline")
    append_lineage_event(
        saved["doc_id"], "raw", {"path": saved["path"], "hash": digest}, lineage_dir=lineage_dir
    )

    cleaned = clean_text(Path(saved["path"]).read_text(encoding="utf-8"))
    chunks = chunk_text(cleaned, size=120, overlap=20)
    assert chunks
    append_lineage_event(
        saved["doc_id"], "chunk", {"chunk_count": len(chunks)}, lineage_dir=lineage_dir
    )

    analysis = run_compliance_analysis(
        {"doc_id": saved["doc_id"], "regulator_id": "gstn", "text": cleaned}
    )
    assert analysis["obligation_count"] >= 1
    append_lineage_event(
        saved["doc_id"],
        "llm_output",
        {"obligation_count": analysis["obligation_count"]},
        lineage_dir=lineage_dir,
    )

    validation = process_validation_job(
        {
            "doc_id": saved["doc_id"],
            "obligations": analysis["obligations"],
        }
    )
    # validation lineage writes to default dir — that's fine for this assertion on custom dir stages
    assert validation["validation"]["passed"] is True
    append_lineage_event(
        saved["doc_id"],
        "rule_validation",
        {"passed": True},
        lineage_dir=lineage_dir,
    )

    report = generate_report_stub("compliance_summary", {"doc_id": saved["doc_id"], "analysis": analysis})
    assert report["status"] == "ok"
    send_slack_stub("dry-run compliance complete")
    send_email_stub("ops@example.com", "RegGraph dry-run", "pipeline ok")
    dashboard_refresh_stub("main")
    append_lineage_event(
        saved["doc_id"], "final_report", {"report_type": report["report_type"]}, lineage_dir=lineage_dir
    )

    events = read_lineage_events(saved["doc_id"], lineage_dir=lineage_dir)
    stages = {e["stage"] for e in events}
    assert {"raw", "chunk", "llm_output", "rule_validation", "final_report"} <= stages
