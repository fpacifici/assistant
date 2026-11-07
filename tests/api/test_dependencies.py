"""Tests for the request session: when it commits, rolls back and closes."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from assistant.api.dependencies import SessionDep


class _RecordingSession:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def commit(self) -> None:
        self._events.append("commit")

    def rollback(self) -> None:
        self._events.append("rollback")

    def close(self) -> None:
        self._events.append("close")


def _app(events: list[str]) -> FastAPI:
    app = FastAPI()
    app.state.session_factory = lambda: _RecordingSession(events)

    @app.post("/write")
    def write(session: SessionDep) -> StreamingResponse:  # noqa: ARG001
        def body() -> Iterator[bytes]:
            events.append("response sent")
            yield b"{}"

        return StreamingResponse(body(), media_type="application/json")

    @app.post("/fail")
    def fail(session: SessionDep) -> None:  # noqa: ARG001
        raise HTTPException(status_code=409, detail="no")

    return app


# --- Session lifecycle ---


def test_a_write_is_committed_before_the_response_is_sent() -> None:
    events: list[str] = []
    with TestClient(_app(events)) as client:
        assert client.post("/write").status_code == 200
    assert events == ["commit", "response sent", "close"]


def test_a_failure_rolls_back_and_commits_nothing() -> None:
    events: list[str] = []
    with TestClient(_app(events)) as client:
        assert client.post("/fail").status_code == 409
    assert events == ["rollback", "close"]
