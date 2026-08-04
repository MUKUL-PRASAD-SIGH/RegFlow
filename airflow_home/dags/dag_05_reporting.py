"""RegGraph AI v2 — dataset-triggered reporting and notification DAG."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from airflow.datasets import Dataset
from airflow.decorators import dag, task

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
    dag_id="reggraph_reporting",
    schedule=[COMPLIANCE_RESULTS],
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["reggraph", "v2", "reporting"],
)
def reggraph_reporting():
    @task
    def publish_report() -> dict:
        import json

        from services.orchestration.lineage import append_lineage_event
        from services.orchestration.metrics import MetricsStore
        from services.orchestration.reporting import (
            dashboard_refresh_stub,
            generate_report_stub,
            send_email_stub,
            send_slack_stub,
            webhook_stub,
        )

        compliance_path = PIPELINE_DIR / "compliance" / "latest_analysis.json"
        compliance_data: list | dict = []
        if compliance_path.exists():
            compliance_data = json.loads(compliance_path.read_text(encoding="utf-8"))

        metrics_path = ROOT / "data" / "metrics" / "counters.json"
        metrics = MetricsStore(persist_path=metrics_path).snapshot()

        report_payload = {
            "compliance": compliance_data,
            "metrics": metrics,
        }

        report = generate_report_stub("daily_compliance", report_payload)
        slack = send_slack_stub("RegGraph AI v2 pipeline report is ready.")
        email = send_email_stub(
            to="ops@reggraph.ai",
            subject="RegGraph Daily Compliance Report",
            body=json.dumps(report_payload, indent=2)[:4000],
        )
        webhook = webhook_stub(
            "https://hooks.reggraph.ai/pipeline",
            {"report_type": "daily_compliance", "metrics": metrics},
        )
        dashboard = dashboard_refresh_stub("reggraph-main")

        archive = {
            "report": report,
            "notifications": {
                "slack": slack,
                "email": email,
                "webhook": webhook,
                "dashboard": dashboard,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        reports_dir = PIPELINE_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_id = f"report-{ts}"
        archive_path = reports_dir / f"{report_id}.json"
        archive_path.write_text(json.dumps(archive, indent=2), encoding="utf-8")

        append_lineage_event(
            report_id,
            "final_report",
            {"path": str(archive_path), "record_count": report.get("record_count", 0)},
        )

        return {
            "status": "ok",
            "report_id": report_id,
            "archive_path": str(archive_path),
        }


reggraph_reporting()
