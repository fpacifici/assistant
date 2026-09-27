"""Tests for Sentry user context set by the auth dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import call, patch

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from assistant.models.schema import User


# --- Sentry user context ---


def test_authenticated_request_sets_sentry_user(
    client: TestClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    with patch("assistant.api.dependencies.sentry_sdk.set_user") as set_user:
        response = client.get("/notebook", headers=auth_headers)

    assert response.status_code == 200
    assert set_user.call_args_list[-1] == call(
        {"id": str(test_user.uid), "email": test_user.email}
    )


def test_unauthenticated_request_does_not_set_sentry_user(client: TestClient) -> None:
    with patch("assistant.api.dependencies.sentry_sdk.set_user") as set_user:
        response = client.get("/notebook")

    assert response.status_code == 401
    set_user.assert_not_called()
