"""Static checks for RegGraph AI v2 Airflow DAG files (no Airflow import)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAG_DIR = ROOT / "airflow_home" / "dags"

EXPECTED_DAGS = [
    ("dag_01_regulatory_collection.py", "reggraph_regulatory_collection", True),
    ("dag_02_document_processing.py", "reggraph_document_processing", False),
    ("dag_03_embedding_pipeline.py", "reggraph_embedding_pipeline", False),
    ("dag_04_compliance_intelligence.py", "reggraph_compliance_intelligence", False),
    ("dag_05_reporting.py", "reggraph_reporting", False),
]


def test_all_dag_files_exist():
    for filename, _, _ in EXPECTED_DAGS:
        assert (DAG_DIR / filename).is_file(), f"Missing DAG file: {filename}"


def test_dag_files_contain_dag_id_and_dataset():
    for filename, dag_id, _ in EXPECTED_DAGS:
        content = (DAG_DIR / filename).read_text(encoding="utf-8")
        assert dag_id in content, f"{filename} missing dag_id {dag_id!r}"
        assert "Dataset" in content, f"{filename} missing Dataset reference"


def test_collection_dag_uses_dynamic_task_mapping():
    content = (DAG_DIR / "dag_01_regulatory_collection.py").read_text(encoding="utf-8")
    assert ".expand(" in content, "Collection DAG should use dynamic task mapping (.expand)"


def test_dag_files_bootstrap_repo_root_on_path():
    for filename, _, _ in EXPECTED_DAGS:
        content = (DAG_DIR / filename).read_text(encoding="utf-8")
        assert "sys.path.insert" in content, f"{filename} missing PYTHONPATH bootstrap"
        assert 'parents[2]' in content, f"{filename} should resolve repo root via parents[2]"
