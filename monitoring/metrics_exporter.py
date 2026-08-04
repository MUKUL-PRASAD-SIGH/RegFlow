"""Minimal HTTP exporter for RegGraph orchestration metrics JSON file."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

METRICS_FILE = Path(os.environ.get("METRICS_FILE", "data/pipeline/metrics.json"))
HOST = os.environ.get("METRICS_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("METRICS_EXPORTER_PORT", "9091"))


def load_metrics() -> dict[str, int]:
    if not METRICS_FILE.exists():
        return {}
    try:
        data = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def to_prometheus_lines(counters: dict[str, int]) -> str:
    lines = [
        "# HELP reggraph_metric RegGraph orchestration counter",
        "# TYPE reggraph_metric gauge",
    ]
    for name, value in sorted(counters.items()):
        safe_name = name.replace("-", "_")
        lines.append(f'reggraph_metric{{name="{safe_name}"}} {value}')
    return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/metrics", "/health"):
            self.send_response(404)
            self.end_headers()
            return

        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        counters = load_metrics()
        if self.path == "/metrics":
            body = to_prometheus_lines(counters)
            content_type = "text/plain; version=0.0.4"
        else:
            body = json.dumps(counters, indent=2)
            content_type = "application/json"

        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), MetricsHandler)
    print(f"RegGraph metrics exporter listening on http://{HOST}:{PORT}/metrics")
    server.serve_forever()


if __name__ == "__main__":
    main()
