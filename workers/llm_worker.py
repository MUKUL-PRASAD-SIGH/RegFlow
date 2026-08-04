"""Worker that processes LLM / compliance jobs from the Redis llm queue."""

from __future__ import annotations

import logging
from typing import Any, Callable

from workers.queue_client import QueueClient

logger = logging.getLogger(__name__)

QUEUE = "llm"


def _resolve_llm_handler() -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    try:
        from services.orchestration.llm import process_llm_job
    except ImportError:
        pass
    else:
        return process_llm_job

    try:
        from services.orchestration.compliance import process_compliance_job
    except ImportError:
        return None
    return process_compliance_job


def _stub_compliance(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "job_id": payload.get("job_id"),
        "stub": True,
        "queue": QUEUE,
        "compliance": {"verdict": "stub_pass", "confidence": 0.0},
    }


def process_one(client: QueueClient | None = None) -> bool:
    """
    Dequeue and process a single LLM/compliance job.

    Returns True if a job was processed, False if the queue was empty.
    """
    client = client or QueueClient()
    job = client.dequeue(QUEUE, timeout=5)
    if job is None:
        return False

    handler = _resolve_llm_handler()
    try:
        if handler is not None:
            result = handler(job)
        else:
            result = _stub_compliance(job)
            logger.info("llm compliance stub success job_id=%s", job.get("job_id"))
        client.ack(QUEUE, job)
        logger.debug("llm job complete: %s", result)
        return True
    except Exception:
        client.nack(QUEUE, job, requeue=True)
        raise


def run_loop(client: QueueClient | None = None) -> None:
    """Continuously process LLM jobs until interrupted."""
    client = client or QueueClient()
    logger.info("llm worker started")
    while True:
        try:
            process_one(client)
        except KeyboardInterrupt:
            logger.info("llm worker stopped")
            break
