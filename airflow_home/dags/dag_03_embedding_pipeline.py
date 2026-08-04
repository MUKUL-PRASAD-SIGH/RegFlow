"""RegGraph AI v2 — dataset-triggered embedding upsert DAG."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from airflow.datasets import Dataset
from airflow.decorators import dag, task

CHUNKS = Dataset("reggraph://chunks")
EMBEDDINGS = Dataset("reggraph://embeddings")
PIPELINE_DIR = ROOT / "data" / "pipeline"

default_args = {
    "owner": "reggraph",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}


def _failure_cb(context):
    from services.orchestration.alerts import alert_on_failure

    alert_on_failure(context)


default_args["on_failure_callback"] = _failure_cb


@dag(
    dag_id="reggraph_embedding_pipeline",
    schedule=[CHUNKS],
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["reggraph", "v2", "embedding"],
)
def reggraph_embedding_pipeline():
    @task(outlets=[EMBEDDINGS])
    def upsert_chunk_embeddings() -> dict:
        import json
        import os

        from services.orchestration.embedding_jobs import upsert_embeddings
        from services.orchestration.lineage import append_lineage_event
        from services.orchestration.metrics import MetricsStore

        chunks_dir = PIPELINE_DIR / "chunks"
        persist_dir = os.environ.get("CHROMA_PERSIST_DIR", str(ROOT / "chroma_db"))

        documents: list[dict] = []
        if chunks_dir.exists():
            for chunk_file in sorted(chunks_dir.glob("*.json")):
                record = json.loads(chunk_file.read_text(encoding="utf-8"))
                meta = record.get("metadata") or {}
                documents.append(
                    {
                        "id": record["chunk_id"],
                        "content": record["content"],
                        "domain": record.get("regulator_id") or "unknown",
                        "title": meta.get("title") or "Untitled regulation excerpt",
                        "source": record.get("source_path") or "",
                        "effective_date": meta.get("effective_date") or "",
                    }
                )

        counts = upsert_embeddings(documents, persist_dir=persist_dir)

        queue_note: str | None = None
        try:
            from workers.queue_client import QueueClient

            client = QueueClient()
            for doc in documents:
                client.enqueue(
                    "embed",
                    {
                        "job_id": doc["id"],
                        "chunk_id": doc["id"],
                        "content": doc["content"],
                        "domain": doc["domain"],
                    },
                )
        except Exception as exc:
            queue_note = f"Redis enqueue skipped: {exc}"

        for doc in documents:
            append_lineage_event(
                doc["id"],
                "embedding",
                {"persist_dir": persist_dir},
            )

        if counts.get("upserted", 0):
            metrics_path = ROOT / "data" / "metrics" / "counters.json"
            store = MetricsStore(persist_path=metrics_path)
            store.increment("embeddings_generated", counts["upserted"])

        return {
            "status": "ok",
            "counts": counts,
            "persist_dir": persist_dir,
            "queue_note": queue_note,
        }


reggraph_embedding_pipeline()
