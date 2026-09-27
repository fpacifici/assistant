"""Tests for Sentry initialisation and filtering."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.transport import Transport

from assistant.config import Config
from assistant.observability import drop_unrouted_anonymous_transaction, init_sentry

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

_DSN = "https://key@o1.ingest.sentry.io/1"


def _config(tmp_path: Path, yaml: str = "other_key: value\n") -> Config:
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(yaml)
    return Config(config_path=config_file)


# --- init_sentry ---


def test_init_sentry_without_dsn_is_noop(tmp_path: Path) -> None:
    """No DSN → `sentry_sdk.init` is never called."""
    with (
        patch.dict(os.environ, {"SENTRY_DSN": ""}),
        patch("assistant.observability.sentry_sdk.init") as sdk_init,
    ):
        assert init_sentry(_config(tmp_path)) is False
    sdk_init.assert_not_called()


def test_init_sentry_with_dsn_passes_config(tmp_path: Path) -> None:
    """With a DSN, the SDK gets the configured values plus the fixed options."""
    config = _config(
        tmp_path,
        "sentry:\n"
        "  environment: production\n"
        "  traces_sample_rate: 0.2\n"
        "  profile_session_sample_rate: 0.3\n",
    )
    with (
        patch.dict(os.environ, {"SENTRY_DSN": _DSN}),
        patch("assistant.observability.sentry_sdk.init") as sdk_init,
        patch("assistant.observability.ignore_logger") as ignore,
        patch("assistant.observability.ignore_logger_for_sentry_logs") as ignore_logs,
    ):
        assert init_sentry(config) is True

    sdk_init.assert_called_once()
    kwargs = sdk_init.call_args.kwargs
    integrations = kwargs.pop("integrations")
    assert kwargs == {
        "dsn": _DSN,
        "environment": "production",
        "traces_sample_rate": 0.2,
        "profile_session_sample_rate": 0.3,
        "profile_lifecycle": "trace",
        "send_default_pii": True,
        "enable_logs": True,
        "before_send_transaction": drop_unrouted_anonymous_transaction,
    }
    [logging_integration] = integrations
    assert isinstance(logging_integration, LoggingIntegration)
    ignore.assert_called_once_with("uvicorn.access")
    ignore_logs.assert_called_once_with("uvicorn.access")


def test_init_sentry_forwards_info_logs(tmp_path: Path) -> None:
    """The logging integration forwards INFO+ records as Sentry logs."""
    with (
        patch.dict(os.environ, {"SENTRY_DSN": _DSN}),
        patch("assistant.observability.sentry_sdk.init") as sdk_init,
        patch("assistant.observability.ignore_logger"),
        patch("assistant.observability.ignore_logger_for_sentry_logs"),
    ):
        init_sentry(_config(tmp_path))

    [logging_integration] = sdk_init.call_args.kwargs["integrations"]
    logs_handler = logging_integration._sentry_logs_handler
    assert logs_handler is not None
    assert logs_handler.level == logging.INFO


# --- drop_unrouted_anonymous_transaction ---


def _transaction(source: str, user_id: str | None = None) -> Event:
    event: Event = {
        "type": "transaction",
        "transaction": "/notebook/{notebook_id}",
        "transaction_info": {"source": source},
    }
    if user_id is not None:
        event["user"] = {"id": user_id}
    return event


def test_drop_filter_keeps_routed_anonymous_transaction() -> None:
    event = _transaction("route")
    assert drop_unrouted_anonymous_transaction(event, {}) is event


def test_drop_filter_keeps_unrouted_authenticated_transaction() -> None:
    event = _transaction("url", user_id="u1")
    assert drop_unrouted_anonymous_transaction(event, {}) is event


def test_drop_filter_drops_unrouted_anonymous_transaction() -> None:
    assert drop_unrouted_anonymous_transaction(_transaction("url"), {}) is None


def test_drop_filter_drops_event_without_transaction_info() -> None:
    event: Event = {"type": "transaction", "transaction": "http://x/nope"}
    assert drop_unrouted_anonymous_transaction(event, {}) is None


def test_drop_filter_on_real_fastapi_transactions() -> None:
    """Pin the SDK's `source` values: routed → "route", unmatched → "url"."""
    kept: list[str] = []

    def before_send_transaction(event: Event, hint: Hint) -> Event | None:
        result = drop_unrouted_anonymous_transaction(event, hint)
        if result is not None:
            kept.append(str(result.get("transaction")))
        return result

    app = FastAPI()

    @app.get("/items/{item_id}")
    def items(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    class _NullTransport(Transport):
        def capture_envelope(self, envelope: object) -> None:
            pass

    sentry_sdk.init(
        dsn=_DSN,
        traces_sample_rate=1.0,
        transport=_NullTransport,
        before_send_transaction=before_send_transaction,
        # Only patch what this test needs; auto-enabled integrations (e.g.
        # LangChain) would stay patched for the rest of the test run.
        auto_enabling_integrations=False,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    try:
        # Earlier API tests call `set_user` with Sentry disabled, which leaves
        # a user on the process-wide isolation scope; start from a clean one.
        with sentry_sdk.isolation_scope() as scope:
            scope.set_user(None)
            client = TestClient(app)
            client.get("/items/1")
            client.get("/wp-admin/setup.php")
        sentry_sdk.flush()
    finally:
        sentry_sdk.init()  # reset to a disabled client

    assert kept == ["/items/{item_id}"]
