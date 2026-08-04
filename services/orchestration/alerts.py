"""Failure alerting helpers used by Airflow DAGs and workers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("reggraph.alerts")
_REPO_ROOT = Path(__file__).resolve().parents[2]


def alert_on_failure(context: dict[str, Any] | None = None) -> None:
    """Airflow on_failure_callback — logs, metrics bump, Slack stub. Never raises."""
    context = context or {}
    try:
        task_instance = context.get("task_instance")
        dag = context.get("dag")
        dag_id = getattr(dag, "dag_id", "unknown")
        task_id = getattr(task_instance, "task_id", "unknown")
        run_id = getattr(task_instance, "run_id", context.get("run_id", "unknown"))
        message = f"[RegGraph AI v2] Task failed: {dag_id}.{task_id} run={run_id}"
        logger.error(message)

        try:
            from services.orchestration.reporting import send_slack_stub

            send_slack_stub(message)
        except Exception as exc:
            logger.warning("Slack stub unavailable: %s", exc)

        try:
            from services.orchestration.metrics import MetricsStore

            store = MetricsStore(persist_path=_REPO_ROOT / "data" / "metrics" / "counters.json")
            store.increment("agent_failures")
        except Exception as exc:
            logger.warning("Metrics bump failed: %s", exc)
    except Exception as exc:
        logger.warning("alert_on_failure swallowed error: %s", exc)
