"""CLI entry point for the Assistant API server."""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Uvicorn installs its own logging config (no timestamps). Override the
# formatters so its server and access logs carry a timestamp too.
_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - "
LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": _LOG_FORMAT + "%(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": _LOG_FORMAT + '%(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}


def main() -> int:
    """Run the Assistant API server."""
    parser = argparse.ArgumentParser(
        description="Run the Assistant API server",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",  # nosec B104 - intentional dev-server default
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

    import uvicorn  # noqa: PLC0415

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
        log_config=LOG_CONFIG,
        # Behind nginx, uvicorn only ever sees the proxy's IP and the original
        # scheme is carried in X-Forwarded-Proto/X-Forwarded-For. Trust those
        # headers so request.url.scheme reflects the client's actual scheme
        # (auth.py relies on this to set the `secure` cookie flag correctly).
        # The backend Service isn't exposed outside the cluster, so trusting
        # the immediate peer unconditionally is safe here; narrow it with
        # FORWARDED_ALLOW_IPS if that changes.
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "*"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
