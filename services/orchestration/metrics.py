"""In-memory and optional file/Redis metrics counters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

COUNTER_NAMES = (
    "documents_scraped",
    "embeddings_generated",
    "tokens_used",
    "obligations_extracted",
    "agent_failures",
    "rule_conflicts",
    "queue_length",
)


class MetricsStore:
    """Track orchestration metrics in memory with optional persistence."""

    def __init__(
        self,
        *,
        persist_path: Path | str | None = None,
        redis_url: str | None = None,
        key_prefix: str = "rgai:metrics:",
    ) -> None:
        self._counters: dict[str, int] = {name: 0 for name in COUNTER_NAMES}
        self._persist_path = Path(persist_path) if persist_path else None
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._redis_client: Any = None

        if self._persist_path and self._persist_path.exists():
            self._load_from_file()

    def _redis(self) -> Any | None:
        if not self._redis_url:
            return None
        if self._redis_client is None:
            try:
                import redis

                self._redis_client = redis.from_url(self._redis_url)
            except Exception:
                return None
        return self._redis_client

    def _load_from_file(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for name in COUNTER_NAMES:
                if name in data:
                    self._counters[name] = int(data[name])
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    def increment(self, name: str, amount: int = 1) -> int:
        """Increment a counter and return the new value."""
        if name not in self._counters:
            self._counters[name] = 0
        self._counters[name] += amount
        self._persist()
        return self._counters[name]

    def set(self, name: str, value: int) -> int:
        """Set a counter to an absolute value."""
        self._counters[name] = value
        self._persist()
        return value

    def get(self, name: str) -> int:
        client = self._redis()
        if client is not None:
            try:
                raw = client.get(f"{self._key_prefix}{name}")
                if raw is not None:
                    return int(raw)
            except Exception:
                pass
        return self._counters.get(name, 0)

    def snapshot(self) -> dict[str, int]:
        """Return all counter values."""
        return dict(self._counters)

    def _persist(self) -> None:
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps(self._counters, indent=2),
                encoding="utf-8",
            )

        client = self._redis()
        if client is not None:
            try:
                pipe = client.pipeline()
                for name, value in self._counters.items():
                    pipe.set(f"{self._key_prefix}{name}", value)
                pipe.execute()
            except Exception:
                pass


_default_store: MetricsStore | None = None


def get_metrics_store(**kwargs: Any) -> MetricsStore:
    """Return a process-wide default MetricsStore (lazy singleton)."""
    global _default_store
    if _default_store is None:
        _default_store = MetricsStore(**kwargs)
    return _default_store
