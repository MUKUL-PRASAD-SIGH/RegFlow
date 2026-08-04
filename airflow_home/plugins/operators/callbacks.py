"""Thin re-export so Airflow plugins folder exposes the shared callback."""

from __future__ import annotations

from typing import Any


def alert_on_failure(context: dict[str, Any] | None = None) -> None:
    from services.orchestration.alerts import alert_on_failure as _impl

    _impl(context)
