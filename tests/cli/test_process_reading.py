"""Tests for the command analyzing pending reading links."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.cli import process_reading
from assistant.models.schema import ReadingAnalysisStatus, ReadingLink, User
from assistant.reading.analysis import MAX_ATTEMPTS, Outcome

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from sqlalchemy.orm import Session


@pytest.fixture
def owner(db_session: Session) -> User:
    user = User(email="reader@example.com", firstname="R", lastname="R")
    db_session.add(user)
    db_session.flush()
    return user


def _link(session: Session, owner: User, status: ReadingAnalysisStatus) -> ReadingLink:
    link = ReadingLink(
        owner_id=owner.uid,
        url="https://example.com/a",
        url_key=uuid.uuid4().hex,
        analysis_status=status,
    )
    session.add(link)
    session.flush()
    return link


# --- Pending links ---


def test_only_pending_links_are_listed(db_session: Session, owner: User) -> None:
    pending = _link(db_session, owner, ReadingAnalysisStatus.PENDING)
    _link(db_session, owner, ReadingAnalysisStatus.DONE)
    assert process_reading.pending_link_ids(db_session) == [pending.id]
    assert process_reading.pending_link_ids(db_session, user_id=uuid.uuid4()) == []
    assert process_reading.pending_link_ids(db_session, link_id=pending.id) == [
        pending.id
    ]


# --- Processing ---


def test_each_link_is_tried_until_it_is_no_longer_pending(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    db_session: Session,
    owner: User,
) -> None:
    flaky = _link(db_session, owner, ReadingAnalysisStatus.PENDING)
    broken = _link(db_session, owner, ReadingAnalysisStatus.PENDING)
    script = {
        flaky.id: [Outcome.RETRY, Outcome.DONE],
        broken.id: [Outcome.RETRY] * (MAX_ATTEMPTS - 1) + [Outcome.FAILED],
    }
    processor = MagicMock()
    processor.process.side_effect = lambda link_id: script[link_id].pop(0)
    with patch.object(process_reading, "LinkProcessor", return_value=processor):
        outcomes = process_reading.process_pending(
            db_session_factory,  # type: ignore[arg-type]
            MagicMock(),
        )
    assert outcomes == {Outcome.DONE: 1, Outcome.FAILED: 1}
    assert processor.process.call_count == 2 + MAX_ATTEMPTS


# --- Exit codes ---


def test_ai_disabled_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_reading, "create_link_analyzer", lambda _config: None)
    assert process_reading.main([]) == 1


def test_exit_code_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_reading, "create_link_analyzer", lambda _c: MagicMock())
    monkeypatch.setattr(process_reading, "get_engine", MagicMock())
    monkeypatch.setattr(
        process_reading,
        "process_pending",
        MagicMock(return_value=Counter({Outcome.DONE: 2})),
    )
    assert process_reading.main([]) == 0
    process_reading.process_pending.return_value = Counter({Outcome.FAILED: 1})  # type: ignore[attr-defined]
    assert process_reading.main([]) == 1
