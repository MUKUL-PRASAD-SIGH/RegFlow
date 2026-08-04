"""RegGraph AI v2 — dataset-triggered document cleaning and chunking DAG."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from airflow.datasets import Dataset
from airflow.decorators import dag, task

RAW_DOCUMENTS = Dataset("reggraph://raw_documents")
CHUNKS = Dataset("reggraph://chunks")
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
    dag_id="reggraph_document_processing",
    schedule=[RAW_DOCUMENTS],
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["reggraph", "v2", "processing"],
)
def reggraph_document_processing():
    @task(outlets=[CHUNKS])
    def process_raw_documents() -> dict:
        import json

        from services.orchestration.lineage import append_lineage_event
        from services.orchestration.processing import (
            chunk_text,
            clean_text,
            extract_metadata,
        )

        raw_dir = PIPELINE_DIR / "raw"
        chunks_dir = PIPELINE_DIR / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        if not raw_dir.exists():
            return {"status": "ok", "processed": 0, "details": []}

        processed: list[dict] = []
        for regulator_dir in sorted(raw_dir.iterdir()):
            if not regulator_dir.is_dir():
                continue

            files = sorted(
                regulator_dir.glob("*.txt"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not files:
                continue

            newest = files[0]
            raw_text = newest.read_text(encoding="utf-8")
            regulator_id = regulator_dir.name
            doc_id = f"{regulator_id}_{newest.stem}"

            cleaned = clean_text(raw_text)
            metadata = extract_metadata(raw_text, regulator_id=regulator_id)

            append_lineage_event(
                doc_id,
                "parsed",
                {"path": str(newest), **metadata},
            )

            chunks = chunk_text(cleaned)
            chunk_records: list[dict] = []
            for idx, chunk in enumerate(chunks):
                chunk_id = f"{doc_id}_chunk_{idx}"
                record = {
                    "chunk_id": chunk_id,
                    "regulator_id": regulator_id,
                    "content": chunk,
                    "metadata": metadata,
                    "source_path": str(newest),
                }
                chunk_path = chunks_dir / f"{chunk_id}.json"
                chunk_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
                chunk_records.append(record)

            append_lineage_event(
                doc_id,
                "chunk",
                {"chunk_count": len(chunks), "source": str(newest)},
            )
            processed.append(
                {
                    "regulator_id": regulator_id,
                    "doc_id": doc_id,
                    "chunk_count": len(chunks),
                }
            )

        return {"status": "ok", "processed": len(processed), "details": processed}


reggraph_document_processing()
