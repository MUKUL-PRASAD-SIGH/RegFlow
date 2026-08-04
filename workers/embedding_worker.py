"""Worker that processes embedding jobs from the Redis embed queue."""

from __future__ import annotations

import logging
from typing import Any, Callable

from workers.queue_client import QueueClient

logger = logging.getLogger(__name__)

QUEUE = "embed"


def _resolve_embedding_handler() -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    try:
        from services.orchestration.embedding import process_embedding_job
    except ImportError:
        return None
    return process_embedding_job


def _stub_embedding(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "job_id": payload.get("job_id"),
        "stub": True,
        "queue": QUEUE,
    }


def process_one(client: QueueClient | None = None) -> bool:
    """
    Dequeue and process a single embed job.

    Returns True if a job was processed, False if the queue was empty.
    """
    client = client or QueueClient()
    job = client.dequeue(QUEUE, timeout=5)
    if job is None:
        return False

    handler = _resolve_embedding_handler()
    try:
        if handler is not None:
            result = handler(job)
        else:
            result = _stub_embedding(job)
            logger.info("embed stub success job_id=%s", job.get("job_id"))
        client.ack(QUEUE, job)
        logger.debug("embed job complete: %s", result)
        return True
    except Exception:
        client.nack(QUEUE, job, requeue=True)
        raise


def run_loop(client: QueueClient | None = None) -> None:
    """Continuously process embed jobs until interrupted."""
    client = client or QueueClient()
    logger.info("embedding worker started")
    while True:
        try:
            process_one(client)
        except KeyboardInterrupt:
            logger.info("embedding worker stopped")
            break
