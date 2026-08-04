"""Reporting and notification stubs (no-op safe without secrets)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _stub_response(channel: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "skipped",
        "channel": channel,
        "sent": False,
        "reason": "no credentials configured",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def generate_report_stub(report_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate a placeholder report payload without external services."""
    return {
        "status": "ok",
        "report_type": report_type,
        "generated": True,
        "record_count": len(data) if data else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def send_slack_stub(message: str, channel: str | None = None) -> dict[str, Any]:
    """No-op Slack sender."""
    return _stub_response(
        "slack",
        message_preview=message[:120],
        slack_channel=channel,
    )


def send_email_stub(
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """No-op email sender."""
    return _stub_response("email", to=to, subject=subject, body_length=len(body))


def webhook_stub(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """No-op webhook caller."""
    return _stub_response("webhook", url=url, payload_keys=list((payload or {}).keys()))


def dashboard_refresh_stub(dashboard_id: str | None = None) -> dict[str, Any]:
    """No-op dashboard refresh trigger."""
    return {
        "status": "ok",
        "refreshed": False,
        "dashboard_id": dashboard_id,
        "reason": "stub — no live dashboard hook configured",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
