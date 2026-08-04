#!/usr/bin/env python3
"""Validate docker-compose.yml by running `docker compose config`."""

from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    if shutil.which("docker") is None:
        print("docker not found; skipping compose validation")
        return 0

    try:
        subprocess.run(
            ["docker", "compose", "config"],
            check=True,
        )
    except subprocess.CalledProcessError:
        print("docker compose config: FAILED", file=sys.stderr)
        return 1

    print("docker compose config: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
