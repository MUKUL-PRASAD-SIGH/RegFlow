"""Integration: dry-run full v2 pipeline without Airflow or live portals."""

from __future__ import annotations

import os
from pathlib import Path


def test_e2e_dry_run_pipeline(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("REGGRAPH_SKIP_CHROMA", "1")
    from services.orchestration.pipeline import run_full_pipeline
    from services.orchestration.lineage import read_lineage_events

    mock_bodies = {
        "gstn": (
            "Title: GST Circular 12\n"
            "Effective date: 2024-04-01\n"
            "Taxpayers must file GSTR-3B monthly before the due date. "
            "Registered persons shall maintain invoice records for six years."
        ),
        "epfo": (
            "Title: EPFO Notice\n"
            "Employers must deposit PF contributions by the 15th. "
            "Establishments shall update UAN details promptly."
        ),
        "fssai": "Title: FSSAI Advisory\nFood businesses must renew licenses annually.",
        "pt": "Title: PT Update\nEmployers shall remit professional tax each month.",
    }

    result = run_full_pipeline(base_dir=tmp_path, mock_bodies=mock_bodies)
    assert result["status"] == "ok"
    stages = result["stages"]
    assert stages["collection"]["saved"] >= 1
    assert stages["processing"]["processed"] >= 1
    assert stages["embedding"]["document_count"] >= 1
    assert stages["compliance"]["analyzed"] >= 1
    assert stages["reporting"]["report_id"].startswith("report-")
    assert (tmp_path / "reports").exists()
    assert (tmp_path / "compliance" / "latest_analysis.json").exists()

    events = read_lineage_events(lineage_dir=tmp_path / "lineage")
    stages_seen = {e["stage"] for e in events}
    assert "raw" in stages_seen
    assert "chunk" in stages_seen
    assert "final_report" in stages_seen
