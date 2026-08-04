"""Sensors for RegGraph AI v2 pipelines."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

try:
    from airflow.sensors.base import BaseSensorOperator
except ImportError:  # pragma: no cover - Airflow only in runtime image
    BaseSensorOperator = object  # type: ignore


class NewRawDocumentsSensor(BaseSensorOperator):
    """
    Succeeds when at least one raw document exists under data/pipeline/raw.

    Useful as an alternative/complement to Dataset scheduling in demos.
    """

    template_fields = ("pipeline_dir",)

    def __init__(
        self,
        *,
        pipeline_dir: str = "/opt/airflow/reggraph/data/pipeline",
        poke_interval: int = 60,
        timeout: int = 60 * 60,
        mode: str = "reschedule",
        **kwargs,
    ) -> None:
        super().__init__(
            poke_interval=poke_interval,
            timeout=timeout,
            mode=mode,
            **kwargs,
        )
        self.pipeline_dir = pipeline_dir

    def poke(self, context) -> bool:  # noqa: ANN001
        raw_dir = Path(self.pipeline_dir) / "raw"
        if not raw_dir.exists():
            self.log.info("Waiting for raw documents at %s", raw_dir)
            return False
        for regulator_dir in raw_dir.iterdir():
            if regulator_dir.is_dir() and any(regulator_dir.glob("*.txt")):
                self.log.info("Found raw documents under %s", regulator_dir)
                return True
        self.log.info("No raw *.txt files yet under %s (checked %s)", raw_dir, datetime.utcnow())
        return False
