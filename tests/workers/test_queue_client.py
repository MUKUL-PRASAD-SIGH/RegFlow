"""Tests for workers.queue_client.

Optional: install fakeredis for in-memory Redis simulation::

    pip install fakeredis

When fakeredis is not installed, tests use unittest.mock MagicMock.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from workers.queue_client import (
    QUEUE_NAMES,
    QueueClient,
    RedisUnavailableError,
    deserialize_payload,
    processing_key,
    queue_key,
    serialize_payload,
)

try:
    import fakeredis

    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False


class TestSerializationHelpers:
    def test_serialize_deserialize_roundtrip(self) -> None:
        payload = {"job_id": "abc-123", "text": "GST filing deadline", "n": 42}
        raw = serialize_payload(payload)
        assert deserialize_payload(raw) == payload

    def test_deserialize_rejects_non_object(self) -> None:
        with pytest.raises(ValueError, match="JSON object"):
            deserialize_payload(json.dumps(["not", "a", "dict"]))

    def test_queue_key_known_and_raw(self) -> None:
        assert queue_key("embed") == QUEUE_NAMES["embed"]
        assert queue_key("rg:queue:custom") == "rg:queue:custom"

    def test_queue_key_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown queue"):
            queue_key("unknown")

    def test_processing_key_suffix(self) -> None:
        assert processing_key("embed") == f"{QUEUE_NAMES['embed']}:processing"


@pytest.fixture
def fake_redis():
    if HAS_FAKEREDIS:
        return fakeredis.FakeRedis(decode_responses=True)
    mock = MagicMock()
    mock.ping.return_value = True
    store: dict[str, list[str]] = {}

    def rpush(key: str, value: str) -> int:
        store.setdefault(key, []).append(value)
        return len(store[key])

    def brpoplpush(src: str, dst: str, timeout: int = 0) -> str | None:
        src_list = store.get(src, [])
        if not src_list:
            return None
        value = src_list.pop()
        store.setdefault(dst, []).insert(0, value)
        return value

    def lrem(key: str, count: int, value: str) -> int:
        lst = store.get(key, [])
        removed = 0
        while count != 0 and value in lst:
            lst.remove(value)
            removed += 1
            if count > 0:
                count -= 1
        store[key] = lst
        return removed

    mock.rpush.side_effect = rpush
    mock.brpoplpush.side_effect = brpoplpush
    mock.lrem.side_effect = lrem
    mock._store = store
    return mock


class TestQueueClient:
    def test_enqueue_assigns_job_id(self, fake_redis) -> None:
        client = QueueClient(client=fake_redis)
        job_id = client.enqueue("embed", {"text": "hello"})
        assert job_id
        key = queue_key("embed")
        if HAS_FAKEREDIS:
            assert fake_redis.llen(key) == 1
            raw = fake_redis.lindex(key, 0)
        else:
            assert len(fake_redis._store[key]) == 1
            raw = fake_redis._store[key][0]
        payload = deserialize_payload(raw)
        assert payload["job_id"] == job_id
        assert payload["text"] == "hello"

    def test_dequeue_moves_to_processing(self, fake_redis) -> None:
        client = QueueClient(client=fake_redis)
        job_id = client.enqueue("llm", {"prompt": "compliance check"})
        job = client.dequeue("llm", timeout=1)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["prompt"] == "compliance check"
        assert "_raw" in job
        assert fake_redis.llen(queue_key("llm")) == 0 if HAS_FAKEREDIS else len(fake_redis._store.get(queue_key("llm"), [])) == 0
        proc = processing_key("llm")
        assert fake_redis.llen(proc) == 1 if HAS_FAKEREDIS else len(fake_redis._store.get(proc, [])) == 1

    def test_dequeue_empty_returns_none(self, fake_redis) -> None:
        client = QueueClient(client=fake_redis)
        assert client.dequeue("validate", timeout=0) is None

    def test_ack_removes_from_processing(self, fake_redis) -> None:
        client = QueueClient(client=fake_redis)
        client.enqueue("validate", {"doc_id": "d1"})
        job = client.dequeue("validate", timeout=1)
        assert job is not None
        client.ack("validate", job)
        proc = processing_key("validate")
        assert fake_redis.llen(proc) == 0 if HAS_FAKEREDIS else len(fake_redis._store.get(proc, [])) == 0

    def test_nack_requeues_job(self, fake_redis) -> None:
        client = QueueClient(client=fake_redis)
        client.enqueue("embed", {"doc_id": "d2"})
        job = client.dequeue("embed", timeout=1)
        assert job is not None
        client.nack("embed", job, requeue=True)
        key = queue_key("embed")
        assert fake_redis.llen(key) == 1 if HAS_FAKEREDIS else len(fake_redis._store[key]) == 1
        proc = processing_key("embed")
        assert fake_redis.llen(proc) == 0 if HAS_FAKEREDIS else len(fake_redis._store.get(proc, [])) == 0

    def test_redis_connection_error_raises_clear_message(self, monkeypatch) -> None:
        broken = MagicMock()
        broken.ping.side_effect = ConnectionError("connection refused")

        import workers.queue_client as qc

        monkeypatch.setattr(qc.redis, "from_url", lambda *args, **kwargs: broken)

        client = QueueClient(redis_url="redis://localhost:56379/0")
        with pytest.raises(RedisUnavailableError, match="Cannot connect to Redis"):
            client.enqueue("embed", {"x": 1})
