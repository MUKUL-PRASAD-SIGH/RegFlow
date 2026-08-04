"""Compliance analysis jobs (mock-safe, no live LLM required)."""

from __future__ import annotations

import re
from typing import Any

_OBLIGATION_RE = re.compile(
    r"(?im)(?:must|shall|required to|mandatory|obliged to)\s+[^.\n]{10,200}"
)


def _deterministic_obligations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract obligation-like structures from payload text fields."""
    text_parts: list[str] = []
    for key in ("text", "content", "body", "regulation_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            text_parts.append(value)

    regulations = payload.get("regulations")
    if isinstance(regulations, list):
        for item in regulations:
            if isinstance(item, dict):
                for field in ("text", "content", "description", "summary"):
                    val = item.get(field)
                    if isinstance(val, str) and val.strip():
                        text_parts.append(val)
            elif isinstance(item, str):
                text_parts.append(item)

    combined = "\n".join(text_parts)
    obligations: list[dict[str, Any]] = []
    for idx, match in enumerate(_OBLIGATION_RE.findall(combined)):
        obligations.append(
            {
                "id": f"obl-{idx + 1}",
                "text": match.strip(),
                "severity": "medium",
                "source": payload.get("regulator_id") or payload.get("source") or "unknown",
            }
        )

    if not obligations and combined.strip():
        obligations.append(
            {
                "id": "obl-1",
                "text": combined.strip()[:500],
                "severity": "low",
                "source": payload.get("regulator_id") or "unknown",
            }
        )

    return obligations


def run_compliance_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Run compliance analysis on a payload.

    Attempts to use ComplianceOrchestrator when importable; otherwise returns
    a deterministic stub suitable for tests and offline pipelines.
    """
    try:
        from services.agents.orchestrator import ComplianceOrchestrator  # noqa: F401

        # Full orchestrator requires async DB session and LangGraph — not suitable
        # for sync worker stubs; fall through to deterministic extraction.
        _ = ComplianceOrchestrator
    except Exception:
        pass

    obligations = _deterministic_obligations(payload)
    return {
        "status": "ok",
        "mode": "stub",
        "obligations": obligations,
        "obligation_count": len(obligations),
        "regulator_id": payload.get("regulator_id"),
        "doc_id": payload.get("doc_id"),
    }
