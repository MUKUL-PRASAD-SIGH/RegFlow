"""RegGraph AI v2 — dataset-triggered compliance analysis DAG."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from airflow.datasets import Dataset
from airflow.decorators import dag, task

EMBEDDINGS = Dataset("reggraph://embeddings")
COMPLIANCE_RESULTS = Dataset("reggraph://compliance_results")
PIPELINE_DIR = ROOT / "data" / "pipeline"

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
    dag_id="reggraph_compliance_intelligence",
    schedule=[EMBEDDINGS],
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["reggraph", "v2", "compliance"],
)
def reggraph_compliance_intelligence():
    @task(outlets=[COMPLIANCE_RESULTS])
    def analyze_compliance() -> dict:
        import json

        from services.orchestration.compliance_jobs import run_compliance_analysis
        from services.orchestration.lineage import append_lineage_event
        from services.orchestration.metrics import MetricsStore

        chunks_dir = PIPELINE_DIR / "chunks"
        results: list[dict] = []

        if chunks_dir.exists():
            chunk_files = sorted(
                chunks_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:50]
            for chunk_file in chunk_files:
                record = json.loads(chunk_file.read_text(encoding="utf-8"))
                payload = {
                    "text": record.get("content") or "",
                    "regulator_id": record.get("regulator_id"),
                    "doc_id": record.get("chunk_id"),
                }
                analysis = run_compliance_analysis(payload)
                results.append(analysis)

                append_lineage_event(
                    record["chunk_id"],
                    "compliance",
                    {
                        "obligation_count": analysis.get("obligation_count", 0),
                        "mode": analysis.get("mode"),
                    },
                )

        queue_notes: list[str] = []
        try:
            from workers.queue_client import QueueClient

            client = QueueClient()
            for result in results:
                client.enqueue("llm", {"job_id": result.get("doc_id"), "payload": result})
                client.enqueue(
                    "validate",
                    {
                        "job_id": result.get("doc_id"),
                        "doc_id": result.get("doc_id"),
                        "obligations": result.get("obligations") or [],
                    },
                )
        except Exception as exc:
            queue_notes.append(str(exc))

        obligation_total = sum(r.get("obligation_count", 0) for r in results)
        if obligation_total:
            metrics_path = ROOT / "data" / "metrics" / "counters.json"
            store = MetricsStore(persist_path=metrics_path)
            store.increment("obligations_extracted", obligation_total)

        compliance_dir = PIPELINE_DIR / "compliance"
        compliance_dir.mkdir(parents=True, exist_ok=True)
        summary_path = compliance_dir / "latest_analysis.json"
        summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

        return {
            "status": "ok",
            "analyzed": len(results),
            "obligation_total": obligation_total,
            "summary_path": str(summary_path),
            "queue_notes": queue_notes,
        }


reggraph_compliance_intelligence()
