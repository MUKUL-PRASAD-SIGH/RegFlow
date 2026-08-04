"""RegGraph AI v2 — hourly regulatory document collection DAG."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from airflow.datasets import Dataset
from airflow.decorators import dag, task

RAW_DOCUMENTS = Dataset("reggraph://raw_documents")
PIPELINE_DIR = ROOT / "data" / "pipeline"
HASH_DIR = ROOT / "data" / "raw" / "_hashes"

default_args = {
    "owner": "reggraph",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
}


def _failure_cb(context):
    from services.orchestration.alerts import alert_on_failure

    alert_on_failure(context)


default_args["on_failure_callback"] = _failure_cb


@dag(
    dag_id="reggraph_regulatory_collection",
    schedule="@hourly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["reggraph", "v2", "collection"],
)
def reggraph_regulatory_collection():
    @task
    def load_enabled_regulators() -> list[dict]:
        from services.orchestration.regulators import get_enabled_regulators

        return [
            {
                "id": r.id,
                "name": r.name,
                "url": r.url,
                "source_type": r.source_type,
            }
            for r in get_enabled_regulators()
            if r.url
        ]

    @task(outlets=[RAW_DOCUMENTS])
    def collect_regulator(regulator: dict) -> dict:
        from services.orchestration.collection import (
            detect_change,
            fetch_url,
            save_raw_document,
        )
        from services.orchestration.lineage import append_lineage_event
        from services.orchestration.metrics import MetricsStore

        regulator_id = regulator["id"]
        url = regulator["url"]

        try:
            result = fetch_url(url)
            if result.get("error"):
                return {
                    "status": "error",
                    "regulator_id": regulator_id,
                    "error": result["error"],
                }

            body = result.get("body") or ""
            HASH_DIR.mkdir(parents=True, exist_ok=True)
            hash_file = HASH_DIR / f"{regulator_id}.txt"
            previous_hash = (
                hash_file.read_text(encoding="utf-8").strip()
                if hash_file.exists()
                else None
            )

            if not detect_change(previous_hash, body):
                return {"status": "unchanged", "regulator_id": regulator_id}

            saved = save_raw_document(regulator_id, body, PIPELINE_DIR)
            hash_file.write_text(saved["content_hash"], encoding="utf-8")

            append_lineage_event(
                saved["doc_id"],
                "raw",
                {
                    "regulator_id": regulator_id,
                    "path": saved["path"],
                    "content_hash": saved["content_hash"],
                },
            )

            metrics_path = ROOT / "data" / "metrics" / "counters.json"
            store = MetricsStore(persist_path=metrics_path)
            store.increment("documents_scraped")

            return {
                "status": "saved",
                "regulator_id": regulator_id,
                "doc_id": saved["doc_id"],
                "path": saved["path"],
            }
        except Exception as exc:
            return {
                "status": "error",
                "regulator_id": regulator_id,
                "error": str(exc),
            }

    regulators = load_enabled_regulators()
    collect_regulator.expand(regulator=regulators)


reggraph_regulatory_collection()
