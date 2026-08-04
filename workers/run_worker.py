"""CLI entrypoint for RegGraph AI v2 Redis queue workers."""

from __future__ import annotations

import argparse
import logging
import sys

from workers.embedding_worker import run_loop as run_embed_loop
from workers.llm_worker import run_loop as run_llm_loop
from workers.queue_client import RedisUnavailableError
from workers.validation_worker import run_loop as run_validate_loop

WORKERS = {
    "embed": run_embed_loop,
    "llm": run_llm_loop,
    "validate": run_validate_loop,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a RegGraph AI v2 Redis queue worker")
    parser.add_argument(
        "--queue",
        required=True,
        choices=sorted(WORKERS),
        help="Queue worker to run (embed, llm, or validate)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    try:
        WORKERS[args.queue]()
    except RedisUnavailableError as exc:
        logging.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
