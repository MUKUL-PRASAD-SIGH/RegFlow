"""Load regulator configuration from YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "regulators.yaml"

# Fallback URLs for disabled/placeholder regulators when env var is unset.
_PLACEHOLDER_URLS: dict[str, str] = {
    "REGULATOR_SEBI_URL": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do",
    "REGULATOR_RBI_URL": "https://www.rbi.org.in/",
    "REGULATOR_MCA_URL": "https://www.mca.gov.in/",
    "REGULATOR_GST_URL": "https://gstcouncil.gov.in/",
    "MOCK_GSTN_URL": "https://gstn-xi.vercel.app/",
    "MOCK_EPFO_URL": "https://epfo-coral.vercel.app/",
    "MOCK_FSSAI_URL": "https://fssai-nine.vercel.app/",
    "MOCK_PT_URL": "https://state-pt.vercel.app/",
}


@dataclass(frozen=True)
class Regulator:
    id: str
    name: str
    source_type: str
    url_env: str
    enabled: bool
    url: str | None = None


def _resolve_url(url_env: str) -> str | None:
    value = os.environ.get(url_env) or _PLACEHOLDER_URLS.get(url_env)
    return value or None


def load_regulators(config_path: Path | None = None) -> list[Regulator]:
    """Load all regulators from YAML with resolved URLs where available."""
    path = config_path or _DEFAULT_CONFIG
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    regulators: list[Regulator] = []
    for entry in raw.get("regulators", []):
        url_env = entry["url_env"]
        regulators.append(
            Regulator(
                id=entry["id"],
                name=entry["name"],
                source_type=entry["source_type"],
                url_env=url_env,
                enabled=bool(entry.get("enabled", False)),
                url=_resolve_url(url_env),
            )
        )
    return regulators


def get_enabled_regulators(config_path: Path | None = None) -> list[Regulator]:
    """Return only regulators marked enabled in config."""
    return [r for r in load_regulators(config_path) if r.enabled]
