"""Sentry error reporting, tracing, profiling and logs.

`init_sentry()` is called once per process by entrypoints that want to be
instrumented (currently only the API server, from `create_app()`). Without a
configured DSN it is a no-op, so local dev and tests run with Sentry off.

See docs/architecture/observability.md.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sentry_sdk
from sentry_sdk.integrations.logging import (
    LoggingIntegration,
    ignore_logger,
    ignore_logger_for_sentry_logs,
)

from assistant.config import Config

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

logger = logging.getLogger(__name__)

# Access log lines duplicate the transactions the FastAPI integration records.
_IGNORED_LOGGERS = ("uvicorn.access",)


def drop_unrouted_anonymous_transaction(event: Event, hint: Hint) -> Event | None:
    """`before_send_transaction` hook dropping unrouted, unauthenticated traffic.

    A request that matches an API route has its transaction named after the
    route template with `transaction_info.source == "route"`. Anything else
    (scanners probing `/wp-admin`, typos) is dropped unless a user was
    identified on the scope, since dead links hit by real users are worth
    seeing. Errors are not affected: this only filters transactions.

    Args:
        event: The transaction event about to be sent.
        hint: Unused SDK hint.

    Returns:
        The event unchanged, or `None` to drop it.
    """
    del hint
    source = event.get("transaction_info", {}).get("source")
    user_id = event.get("user", {}).get("id")
    if source != "route" and not user_id:
        return None
    return event


def init_sentry(config: Config | None = None) -> bool:
    """Initialise the Sentry SDK from config.

    Args:
        config: Config to read `sentry.*` from; defaults to `Config()`.

    Returns:
        `True` if the SDK was initialised, `False` (no-op) when no DSN is set.
    """
    sentry_config = (config or Config()).get_sentry_config()
    dsn = sentry_config["dsn"]
    if not dsn:
        logger.info("Sentry disabled: no DSN configured")
        return False

    for name in _IGNORED_LOGGERS:
        ignore_logger(name)
        ignore_logger_for_sentry_logs(name)

    sentry_sdk.init(
        dsn=dsn,
        environment=sentry_config["environment"],
        traces_sample_rate=sentry_config["traces_sample_rate"],
        profile_session_sample_rate=sentry_config["profile_session_sample_rate"],
        profile_lifecycle="trace",
        send_default_pii=True,
        enable_logs=True,
        before_send_transaction=drop_unrouted_anonymous_transaction,
        integrations=[LoggingIntegration(sentry_logs_level=logging.INFO)],
    )
    return True
