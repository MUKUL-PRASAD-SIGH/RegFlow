"""Document collection helpers for regulator portals."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def content_hash(text: str) -> str:
    """Return SHA-256 hex digest of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_url(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    """
    Fetch a URL synchronously.

    Returns a dict with keys: status, body, content_type, error.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
        return {
            "status": response.status_code,
            "body": response.text,
            "content_type": response.headers.get("content-type", ""),
            "error": None if response.is_success else f"HTTP {response.status_code}",
        }
    except Exception as exc:
        return {
            "status": None,
            "body": "",
            "content_type": "",
            "error": str(exc),
        }


def detect_change(previous_hash: str | None, body: str) -> bool:
    """Return True when body hash differs from previous_hash (or no prior hash)."""
    current = content_hash(body)
    if previous_hash is None:
        return True
    return current != previous_hash


def save_raw_document(
    regulator_id: str,
    body: str,
    base_dir: Path | str,
) -> dict[str, Any]:
    """
    Persist raw document body under base_dir/raw/{regulator_id}/.

    Returns lineage-ready metadata including path and content hash.
    """
    base = Path(base_dir)
    doc_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    digest = content_hash(body)

    target_dir = base / "raw" / regulator_id
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{digest[:12]}.txt"
    file_path = target_dir / filename
    file_path.write_text(body, encoding="utf-8")

    return {
        "doc_id": doc_id,
        "regulator_id": regulator_id,
        "path": str(file_path),
        "content_hash": digest,
        "size_bytes": len(body.encode("utf-8")),
        "saved_at": timestamp.isoformat(),
    }
