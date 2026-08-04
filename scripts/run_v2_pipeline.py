#!/usr/bin/env python3
"""CLI: run RegGraph AI v2 dry pipeline without Airflow.

Usage:
  python scripts/run_v2_pipeline.py --mock
  python scripts/run_v2_pipeline.py --live
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="RegGraph AI v2 pipeline dry-run")
    parser.add_argument("--mock", action="store_true", help="Use built-in mock regulator texts")
    parser.add_argument("--live", action="store_true", help="Fetch live portal URLs")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "pipeline" / "e2e_runs",
        help="Pipeline working directory",
    )
    parser.add_argument("--skip-chroma", action="store_true", default=True)
    args = parser.parse_args()

    if args.skip_chroma:
        os.environ["REGGRAPH_SKIP_CHROMA"] = "1"

    from services.orchestration.pipeline import run_full_pipeline

    mock_bodies = None
    if args.mock or not args.live:
        mock_bodies = {
            "gstn": "Title: GST Circular\nTaxpayers must file returns monthly. Businesses shall keep records.",
            "epfo": "Title: EPFO Notice\nEmployers must deposit PF by the 15th.",
            "fssai": "Title: FSSAI\nFood businesses must renew licenses annually.",
            "pt": "Title: PT\nEmployers shall remit professional tax each month.",
        }

    args.out.mkdir(parents=True, exist_ok=True)
    result = run_full_pipeline(base_dir=args.out, mock_bodies=mock_bodies)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
