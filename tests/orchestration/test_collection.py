"""Tests for document collection helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.orchestration.collection import (
    content_hash,
    detect_change,
    fetch_url,
    save_raw_document,
)


def test_content_hash_deterministic() -> None:
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")


def test_detect_change_first_run() -> None:
    assert detect_change(None, "body text") is True


def test_detect_change_no_change() -> None:
    body = "same content"
    previous = content_hash(body)
    assert detect_change(previous, body) is False


def test_detect_change_detects_diff() -> None:
    previous = content_hash("old")
    assert detect_change(previous, "new") is True


def test_save_raw_document_writes_file(tmp_path: Path) -> None:
    result = save_raw_document("gstn", "raw portal data", tmp_path)
    assert Path(result["path"]).exists()
    assert result["regulator_id"] == "gstn"
    assert result["content_hash"] == content_hash("raw portal data")
    assert result["size_bytes"] == len("raw portal data".encode("utf-8"))
    assert "doc_id" in result
    assert "saved_at" in result


def test_fetch_url_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.text = '{"regulations": []}'
    mock_response.headers = {"content-type": "application/json"}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_response

    with patch("services.orchestration.collection.httpx.Client", return_value=mock_client):
        result = fetch_url("https://example.com")

    assert result["status"] == 200
    assert result["body"] == '{"regulations": []}'
    assert result["content_type"] == "application/json"
    assert result["error"] is None


def test_fetch_url_http_error() -> None:
    with patch(
        "services.orchestration.collection.httpx.Client",
        side_effect=Exception("connection failed"),
    ):
        result = fetch_url("https://example.com")

    assert result["status"] is None
    assert result["body"] == ""
    assert result["error"] is not None
