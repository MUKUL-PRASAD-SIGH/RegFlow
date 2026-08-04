"""Text cleaning, chunking, and metadata extraction."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"(?im)^(?:title|subject|heading)\s*[:]\s*(.+)$")
_DATE_RE = re.compile(
    r"(?i)(?:effective|published|issued|dated)\s*(?:on|date)?\s*[:]\s*"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
)


def clean_text(text: str) -> str:
    """Normalize whitespace and strip HTML tags from raw text."""
    without_tags = _HTML_TAG_RE.sub(" ", text)
    normalized = _WHITESPACE_RE.sub(" ", without_tags).strip()
    return normalized


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    """
    Split text into overlapping chunks.

    Raises ValueError when overlap >= size.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    cleaned = clean_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    step = size - overlap
    while start < len(cleaned):
        chunk = cleaned[start : start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(cleaned):
            break
        start += step
    return chunks


def extract_metadata(text: str, *, regulator_id: str | None = None) -> dict[str, Any]:
    """Extract lightweight metadata from document text without LLM calls."""
    cleaned = clean_text(text)
    title_match = _TITLE_RE.search(text)
    date_match = _DATE_RE.search(text)

    title = title_match.group(1).strip() if title_match else None
    if not title:
        first_line = cleaned.split(". ", 1)[0][:120] if cleaned else ""
        title = first_line or "Untitled regulation excerpt"

    effective_date = date_match.group(1) if date_match else None
    word_count = len(cleaned.split()) if cleaned else 0

    return {
        "title": title,
        "regulator_id": regulator_id,
        "effective_date": effective_date,
        "word_count": word_count,
        "char_count": len(cleaned),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
