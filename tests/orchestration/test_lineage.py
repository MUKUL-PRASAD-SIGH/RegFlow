"""Tests for lineage event logging."""

from pathlib import Path

from services.orchestration.lineage import append_lineage_event, read_lineage_events


def test_append_and_read_lineage_event(tmp_path: Path) -> None:
    result = append_lineage_event(
        "doc-123",
        "collected",
        {"regulator_id": "gstn", "hash": "abc"},
        lineage_dir=tmp_path,
    )
    assert Path(result["path"]).exists()
    assert result["event"]["doc_id"] == "doc-123"
    assert result["event"]["stage"] == "collected"

    events = read_lineage_events(lineage_dir=tmp_path)
    assert len(events) == 1
    assert events[0]["meta"]["regulator_id"] == "gstn"


def test_read_lineage_events_filter_by_doc_id(tmp_path: Path) -> None:
    append_lineage_event("doc-a", "collected", lineage_dir=tmp_path)
    append_lineage_event("doc-b", "embedded", lineage_dir=tmp_path)

    filtered = read_lineage_events("doc-a", lineage_dir=tmp_path)
    assert len(filtered) == 1
    assert filtered[0]["doc_id"] == "doc-a"


def test_read_lineage_events_empty_when_missing(tmp_path: Path) -> None:
    assert read_lineage_events(lineage_dir=tmp_path) == []
