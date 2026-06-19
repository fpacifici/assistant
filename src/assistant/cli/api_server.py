"""CLI entry point for the Assistant API server."""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run the Assistant API server."""
    parser = argparse.ArgumentParser(
        description="Run the Assistant API server",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload",
    )
    args = parser.parse_args()

    import uvicorn

    logger.info(
        "Starting API server on %s:%d",
        args.host,
        args.port,
    )
    uvicorn.run(
        "assistant.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
