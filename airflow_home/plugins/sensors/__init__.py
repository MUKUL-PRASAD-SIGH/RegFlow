"""Airflow sensor plugin exports."""

try:
    from airflow.plugins.sensors.new_raw_documents import NewRawDocumentsSensor
except ImportError:
    try:
        from sensors.new_raw_documents import NewRawDocumentsSensor  # type: ignore
    except ImportError:
        NewRawDocumentsSensor = None  # type: ignore

__all__ = ["NewRawDocumentsSensor"]
