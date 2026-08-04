"""Redis list-backed job queue client for RegGraph AI v2 workers."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

try:
    import redis
except ImportError as exc:  # pragma: no cover - redis is a runtime dependency
    redis = None  # type: ignore[assignment]
    _REDIS_IMPORT_ERROR = exc
else:
    _REDIS_IMPORT_ERROR = None

DEFAULT_REDIS_URL = "redis://localhost:56379/0"

QUEUE_NAMES: dict[str, str] = {
    "embed": "rg:queue:embed",
    "llm": "rg:queue:llm",
    "validate": "rg:queue:validate",
}


class RedisUnavailableError(ConnectionError):
    """Raised when Redis cannot be reached or the client library is missing."""


def queue_key(queue: str) -> str:
    """Resolve a logical queue name to its Redis list key."""
    if queue in QUEUE_NAMES:
        return QUEUE_NAMES[queue]
    if queue.startswith("rg:queue:"):
        return queue
    raise ValueError(
        f"Unknown queue {queue!r}. Expected one of: {', '.join(sorted(QUEUE_NAMES))}"
    )


def processing_key(queue: str) -> str:
    """Redis list key used for in-flight jobs (ack / nack pattern)."""
    return f"{queue_key(queue)}:processing"


def serialize_payload(payload: dict[str, Any]) -> str:
    """Serialize a job payload for Redis list storage."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def deserialize_payload(raw: str) -> dict[str, Any]:
    """Deserialize a job payload from Redis."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Queue payload must be a JSON object")
    return data


class QueueClient:
    """Thin wrapper around Redis lists for enqueue / dequeue / ack."""

    def __init__(self, redis_url: str | None = None, client: Any | None = None) -> None:
        self.redis_url = redis_url or os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
        self._client = client

    @property
    def redis(self) -> Any:
        if self._client is not None:
            return self._client
        if redis is None:
            raise RedisUnavailableError(
                "redis package is not installed; install redis to use queue workers"
            ) from _REDIS_IMPORT_ERROR
        try:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
        except (redis.ConnectionError, ConnectionError) as exc:
            raise RedisUnavailableError(
                f"Cannot connect to Redis at {self.redis_url}: {exc}"
            ) from exc
        except redis.RedisError as exc:
            raise RedisUnavailableError(
                f"Redis error for {self.redis_url}: {exc}"
            ) from exc
        except OSError as exc:
            raise RedisUnavailableError(
                f"Cannot reach Redis at {self.redis_url}: {exc}"
            ) from exc
        return self._client

    def enqueue(self, queue: str, payload: dict[str, Any]) -> str:
        """Push a job onto the tail of the queue. Returns job_id."""
        body = dict(payload)
        job_id = str(body.get("job_id") or uuid.uuid4())
        body["job_id"] = job_id
        serialized = serialize_payload(body)
        self.redis.rpush(queue_key(queue), serialized)
        return job_id

    def dequeue(self, queue: str, timeout: int = 5) -> dict[str, Any] | None:
        """
        Atomically move one job from the queue into its processing list.

        Returns None when no job is available within ``timeout`` seconds.
        The returned dict includes ``_raw`` (exact Redis string) for ack/nack.
        """
        key = queue_key(queue)
        proc_key = processing_key(queue)
        raw = self.redis.brpoplpush(key, proc_key, timeout=timeout)
        if raw is None:
            return None
        payload = deserialize_payload(raw)
        payload["_raw"] = raw
        return payload

    def ack(self, queue: str, payload: dict[str, Any]) -> None:
        """Remove a successfully processed job from the processing list."""
        raw = payload.get("_raw")
        if raw is None:
            raw = serialize_payload({k: v for k, v in payload.items() if k != "_raw"})
        self.redis.lrem(processing_key(queue), 1, raw)

    def nack(self, queue: str, payload: dict[str, Any], *, requeue: bool = True) -> None:
        """Drop a failed job from processing and optionally requeue it."""
        raw = payload.get("_raw")
        if raw is None:
            raw = serialize_payload({k: v for k, v in payload.items() if k != "_raw"})
        proc_key = processing_key(queue)
        self.redis.lrem(proc_key, 1, raw)
        if requeue:
            self.redis.rpush(queue_key(queue), raw)
