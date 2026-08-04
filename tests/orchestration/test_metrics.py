"""Tests for metrics counters."""

from pathlib import Path

from services.orchestration.metrics import COUNTER_NAMES, MetricsStore, get_metrics_store


def test_increment_and_snapshot() -> None:
    store = MetricsStore()
    assert store.increment("documents_scraped") == 1
    assert store.increment("documents_scraped", 4) == 5
    snapshot = store.snapshot()
    assert snapshot["documents_scraped"] == 5


def test_set_counter() -> None:
    store = MetricsStore()
    store.set("queue_length", 42)
    assert store.get("queue_length") == 42


def test_persist_to_file(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    store = MetricsStore(persist_path=path)
    store.increment("embeddings_generated", 3)

    reloaded = MetricsStore(persist_path=path)
    assert reloaded.get("embeddings_generated") == 3


def test_all_counter_names_initialized() -> None:
    store = MetricsStore()
    snapshot = store.snapshot()
    for name in COUNTER_NAMES:
        assert name in snapshot


def test_get_metrics_store_singleton() -> None:
    a = get_metrics_store()
    b = get_metrics_store()
    assert a is b
