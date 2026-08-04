"""Tests for regulator YAML loading."""

from pathlib import Path

import yaml

from services.orchestration.regulators import get_enabled_regulators, load_regulators

CONFIG = Path(__file__).resolve().parents[2] / "config" / "regulators.yaml"


def test_config_file_exists() -> None:
    assert CONFIG.exists()


def test_load_all_regulators() -> None:
    regulators = load_regulators(CONFIG)
    assert len(regulators) == 8
    ids = {r.id for r in regulators}
    assert ids == {"gstn", "epfo", "fssai", "pt", "sebi", "rbi", "mca", "gst"}


def test_enabled_regulators() -> None:
    enabled = get_enabled_regulators(CONFIG)
    enabled_ids = {r.id for r in enabled}
    assert enabled_ids == {"gstn", "epfo", "fssai", "pt"}
    assert all(r.enabled for r in enabled)
    assert all(r.url for r in enabled)


def test_disabled_placeholders_have_source_types() -> None:
    regulators = load_regulators(CONFIG)
    disabled = [r for r in regulators if not r.enabled]
    assert len(disabled) == 4
    source_types = {r.source_type for r in disabled}
    assert source_types <= {"portal", "rss", "gazette"}


def test_yaml_schema_keys() -> None:
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for entry in raw["regulators"]:
        assert {"id", "name", "source_type", "url_env", "enabled"} <= set(entry.keys())
