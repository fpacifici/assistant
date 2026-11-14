"""Tests for the reading service: URL identity and what Postgres enforces."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from assistant.models.schema import (
    Note,
    Notebook,
    ReadingLink,
    ReadingLinkState,
    User,
)
from assistant.reading.exceptions import InvalidLinkUrlError
from assistant.reading.service import add_link, normalize_url, url_key

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# --- normalize_url ---


def test_normalize_drops_tracking_and_keeps_the_rest() -> None:
    assert (
        normalize_url("  https://Example.com/a?utm_source=x&id=3&fbclid=y#part  ")
        == "https://Example.com/a?id=3#part"
    )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "example.com/page",
        "javascript:alert(1)",
        "https://",
        "https://" + "a" * 2048 + ".com",
    ],
)
def test_normalize_refuses_what_is_not_http(url: str) -> None:
    with pytest.raises(InvalidLinkUrlError):
        normalize_url(url)


# --- url_key ---


@pytest.mark.parametrize(
    "variant",
    [
        "https://example.com/post",
        "http://example.com/post",
        "https://EXAMPLE.com/post/",
        "https://example.com:443/post",
        "https://example.com/post#comments",
        "https://example.com/post?utm_campaign=z",
    ],
)
def test_spelling_variants_have_one_key(variant: str) -> None:
    assert url_key(variant) == url_key("https://example.com/post")


def test_query_parameter_order_does_not_count() -> None:
    assert url_key("https://example.com/p?a=1&b=2") == url_key(
        "https://example.com/p?b=2&a=1"
    )


@pytest.mark.parametrize(
    "other",
    [
        "https://other.com/post",
        "https://example.com:8443/post",
        "https://example.com/post?id=2",
        "https://example.com/Post",
    ],
)
def test_different_links_have_different_keys(other: str) -> None:
    assert url_key(other) != url_key("https://example.com/post")


# --- Foreign keys (Postgres) ---


@pytest.mark.postgres
def test_deleting_a_note_keeps_the_link_promoted(pg_session: Session) -> None:
    owner = User(email=f"{uuid.uuid4().hex}@example.com", firstname="A", lastname="B")
    pg_session.add(owner)
    pg_session.flush()
    notebook = Notebook(name="nb", owner_id=owner.uid)
    pg_session.add(notebook)
    pg_session.flush()
    now = datetime.now(UTC)
    note = Note(
        title="n",
        notebook_id=notebook.id,
        owner_id=owner.uid,
        update_timestamp=now,
    )
    pg_session.add(note)
    pg_session.flush()
    link = add_link(pg_session, owner, "https://example.com/a")
    link.state = ReadingLinkState.PROMOTED.value
    link.note_id = note.id
    link.decided_at = now
    pg_session.flush()

    pg_session.execute(delete(Note).where(Note.id == note.id))
    pg_session.refresh(link)
    assert link.note_id is None
    assert link.state == ReadingLinkState.PROMOTED.value


@pytest.mark.postgres
def test_the_same_key_is_refused_by_the_database(pg_session: Session) -> None:
    owner = User(email=f"{uuid.uuid4().hex}@example.com", firstname="A", lastname="B")
    pg_session.add(owner)
    pg_session.flush()
    add_link(pg_session, owner, "https://example.com/a")
    duplicate = ReadingLink(
        owner_id=owner.uid,
        url="https://example.com/a/",
        url_key=url_key("https://example.com/a/"),
    )
    pg_session.add(duplicate)
    with pytest.raises(IntegrityError, match="uq_reading_link_owner_url_key"):
        pg_session.flush()
