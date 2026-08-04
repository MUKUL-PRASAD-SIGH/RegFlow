"""Tests for text processing helpers."""

import pytest

from services.orchestration.processing import chunk_text, clean_text, extract_metadata


def test_clean_text_strips_html_and_whitespace() -> None:
    raw = "<p>Hello   <b>world</b></p>\n\n  foo"
    assert clean_text(raw) == "Hello world foo"


def test_chunk_text_single_short_chunk() -> None:
    text = "Short regulation text."
    assert chunk_text(text, size=800) == ["Short regulation text."]


def test_chunk_text_multiple_with_overlap() -> None:
    text = "A" * 1000
    chunks = chunk_text(text, size=400, overlap=50)
    assert len(chunks) >= 2
    assert all(len(c) <= 400 for c in chunks)


def test_chunk_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("text", size=100, overlap=100)


def test_extract_metadata_finds_title_and_date() -> None:
    text = "Title: GST Filing Rule\nEffective date: 2024-01-15\nEntities must file returns."
    meta = extract_metadata(text, regulator_id="gstn")
    assert meta["title"] == "GST Filing Rule"
    assert meta["effective_date"] == "2024-01-15"
    assert meta["regulator_id"] == "gstn"
    assert meta["word_count"] > 0


def test_extract_metadata_fallback_title() -> None:
    text = "Some regulation without explicit title line."
    meta = extract_metadata(text)
    assert meta["title"]
    assert meta["effective_date"] is None
