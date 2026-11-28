"""Tests for note presence: heartbeats, who is active, and the live state."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from assistant.models.schema import Note, NotePresence, RoleName, User
from assistant.notes.avatar_colors import AVATAR_COLORS, avatar_color
from assistant.notes.entitlements import grant_entitlement
from assistant.notes.exceptions import (
    NotebookNotFoundError,
    NoteNotFoundError,
    PresenceClientTakenError,
)
from assistant.notes.presence import (
    PRESENCE_TTL,
    Cursor,
    active_in_notebook,
    active_on_note,
    heartbeat,
    leave,
    live_state,
    note_revision,
)
from assistant.notes.service import (
    add_markdown_node,
    create_note,
    create_notebook,
    update_note,
)
from assistant.notes.user_service import set_avatar_color

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


def _make_user(session: Session, email: str, firstname: str = "Ada") -> User:
    user = User(email=email, firstname=firstname, lastname="Lovelace")
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def owner(db_session: Session) -> User:
    return _make_user(db_session, "owner@test.com", "Olivia")


@pytest.fixture
def editor(db_session: Session) -> User:
    return _make_user(db_session, "editor@test.com", "bob")


@pytest.fixture
def note(db_session: Session, owner: User, editor: User) -> Note:
    notebook = create_notebook(db_session, "NB", owner)
    note = create_note(db_session, notebook.id, owner, "Shared")
    grant_entitlement(
        db_session,
        owner,
        note_id=note.id,
        grantee_email=editor.email,
        role_name=RoleName.NOTE_EDITOR,
    )
    return note


def _rows(session: Session) -> list[NotePresence]:
    return list(session.scalars(select(NotePresence)))


# --- heartbeat ---


def test_heartbeat_records_the_tab_and_its_cursor(
    db_session: Session, note: Note, editor: User
) -> None:
    client = uuid.uuid4()
    node = uuid.uuid4()

    heartbeat(db_session, note.id, editor, client, Cursor(node, 4), now=NOW)

    [row] = _rows(db_session)
    assert (row.note_id, row.client_id, row.user_id) == (note.id, client, editor.uid)
    assert (row.cursor_node_id, row.cursor_offset) == (node, 4)


def test_heartbeat_updates_the_same_row(
    db_session: Session, note: Note, editor: User
) -> None:
    client = uuid.uuid4()
    heartbeat(db_session, note.id, editor, client, Cursor(uuid.uuid4(), 1), now=NOW)

    later = NOW + timedelta(seconds=10)
    heartbeat(db_session, note.id, editor, client, None, now=later)

    [row] = _rows(db_session)
    assert row.cursor_node_id is None
    assert row.cursor_offset is None
    assert row.last_seen.replace(tzinfo=UTC) == later


def test_heartbeat_needs_view_access(db_session: Session, note: Note) -> None:
    stranger = _make_user(db_session, "stranger@test.com")

    with pytest.raises(NoteNotFoundError):
        heartbeat(db_session, note.id, stranger, uuid.uuid4(), None, now=NOW)


def test_heartbeat_refuses_a_client_id_of_another_user(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    client = uuid.uuid4()
    heartbeat(db_session, note.id, editor, client, None, now=NOW)

    with pytest.raises(PresenceClientTakenError):
        heartbeat(db_session, note.id, owner, client, None, now=NOW)


def test_heartbeat_deletes_expired_presences(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    heartbeat(db_session, note.id, editor, uuid.uuid4(), None, now=NOW)

    heartbeat(db_session, note.id, owner, uuid.uuid4(), None, now=NOW + PRESENCE_TTL * 2)

    assert [row.user_id for row in _rows(db_session)] == [owner.uid]


# --- leave ---


def test_leave_deletes_the_tab_and_is_idempotent(
    db_session: Session, note: Note, editor: User
) -> None:
    client = uuid.uuid4()
    heartbeat(db_session, note.id, editor, client, None, now=NOW)

    leave(db_session, note.id, editor, client)
    leave(db_session, note.id, editor, client)

    assert _rows(db_session) == []


def test_leave_only_deletes_the_callers_own_row(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    client = uuid.uuid4()
    heartbeat(db_session, note.id, editor, client, None, now=NOW)

    leave(db_session, note.id, owner, client)

    assert len(_rows(db_session)) == 1


# --- active_on_note ---


def test_active_on_note_lists_others_not_the_caller(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    node = uuid.uuid4()
    heartbeat(db_session, note.id, editor, uuid.uuid4(), Cursor(node, 2), now=NOW)
    heartbeat(db_session, note.id, owner, uuid.uuid4(), None, now=NOW)

    [user] = active_on_note(db_session, note.id, owner, now=NOW)

    assert user.user_id == editor.uid
    assert user.name == "bob Lovelace"
    assert user.initial == "B"
    assert user.cursor == Cursor(node, 2)
    assert active_on_note(db_session, note.id, editor, now=NOW)[0].user_id == owner.uid


def test_active_on_note_shows_a_user_once_with_the_latest_cursor(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    old, new = uuid.uuid4(), uuid.uuid4()
    heartbeat(db_session, note.id, editor, uuid.uuid4(), Cursor(old, 0), now=NOW)
    heartbeat(
        db_session,
        note.id,
        editor,
        uuid.uuid4(),
        Cursor(new, 0),
        now=NOW + timedelta(seconds=1),
    )

    users = active_on_note(db_session, note.id, owner, now=NOW + timedelta(seconds=2))

    assert [u.cursor for u in users] == [Cursor(new, 0)]


def test_active_on_note_ignores_expired_presences(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    heartbeat(db_session, note.id, editor, uuid.uuid4(), None, now=NOW)

    later = NOW + PRESENCE_TTL + timedelta(seconds=1)
    assert active_on_note(db_session, note.id, owner, now=later) == []


def test_initial_falls_back_to_the_email(
    db_session: Session, note: Note, owner: User
) -> None:
    nameless = _make_user(db_session, "zed@test.com", firstname="")
    grant_entitlement(
        db_session,
        owner,
        note_id=note.id,
        grantee_email=nameless.email,
        role_name=RoleName.NOTE_VIEWER,
    )
    heartbeat(db_session, note.id, nameless, uuid.uuid4(), None, now=NOW)

    [user] = active_on_note(db_session, note.id, owner, now=NOW)

    assert user.initial == "Z"


def test_color_is_the_preferred_one_for_every_viewer(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    set_avatar_color(db_session, editor.uid, "pink")
    set_avatar_color(db_session, owner.uid, "blue")
    heartbeat(db_session, note.id, editor, uuid.uuid4(), None, now=NOW)
    heartbeat(db_session, note.id, owner, uuid.uuid4(), None, now=NOW)

    [seen_by_owner] = active_on_note(db_session, note.id, owner, now=NOW)
    [seen_by_editor] = active_on_note(db_session, note.id, editor, now=NOW)

    assert seen_by_owner.color == AVATAR_COLORS["pink"]
    assert seen_by_editor.color == AVATAR_COLORS["blue"]


def test_color_without_a_preference_comes_from_the_palette(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    heartbeat(db_session, note.id, editor, uuid.uuid4(), None, now=NOW)

    [user] = active_on_note(db_session, note.id, owner, now=NOW)

    assert user.color == avatar_color(editor.uid, None)
    assert user.color in AVATAR_COLORS.values()


# --- active_in_notebook ---


def test_active_in_notebook_groups_by_note(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    other = create_note(db_session, note.notebook_id, owner, "Private")
    heartbeat(db_session, note.id, editor, uuid.uuid4(), None, now=NOW)

    entries = active_in_notebook(db_session, note.notebook_id, owner, now=NOW)

    assert [(e.note_id, [u.user_id for u in e.users]) for e in entries] == [
        (note.id, [editor.uid]),
    ]
    assert other.id not in {e.note_id for e in entries}


def test_active_in_notebook_hides_notes_the_caller_cannot_view(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    private = create_note(db_session, note.notebook_id, owner, "Private")
    heartbeat(db_session, private.id, owner, uuid.uuid4(), None, now=NOW)

    assert active_in_notebook(db_session, note.notebook_id, editor, now=NOW) == []


def test_active_in_notebook_needs_the_notebook(db_session: Session, note: Note) -> None:
    stranger = _make_user(db_session, "stranger@test.com")

    with pytest.raises(NotebookNotFoundError):
        active_in_notebook(db_session, note.notebook_id, stranger, now=NOW)


# --- live_state ---


def test_live_state_returns_nodes_when_the_revision_differs(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    add_markdown_node(db_session, note.id, owner, "Hello", "paragraph")
    db_session.refresh(note)

    state = live_state(db_session, note.id, editor, None, now=NOW)

    assert state.revision == note_revision(note)
    assert state.title == "Shared"
    assert state.nodes is not None
    assert [n.payload for n in state.nodes] == ["Hello"]


def test_live_state_omits_nodes_at_the_same_revision(
    db_session: Session, note: Note, editor: User
) -> None:
    revision = live_state(db_session, note.id, editor, None, now=NOW).revision

    state = live_state(db_session, note.id, editor, revision, now=NOW)

    assert state.nodes is None
    assert state.revision == revision


def test_live_state_revision_changes_with_the_title(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    revision = live_state(db_session, note.id, editor, None, now=NOW).revision

    update_note(db_session, note.id, owner, title="Renamed")
    db_session.refresh(note)

    state = live_state(db_session, note.id, editor, revision, now=NOW)
    assert state.revision != revision
    assert state.title == "Renamed"
    assert state.nodes == []


def test_live_state_includes_presence(
    db_session: Session, note: Note, owner: User, editor: User
) -> None:
    heartbeat(db_session, note.id, owner, uuid.uuid4(), None, now=NOW)

    state = live_state(db_session, note.id, editor, None, now=NOW)

    assert [u.user_id for u in state.presence] == [owner.uid]


def test_live_state_needs_view_access(db_session: Session, note: Note) -> None:
    stranger = _make_user(db_session, "stranger@test.com")

    with pytest.raises(NoteNotFoundError):
        live_state(db_session, note.id, stranger, None, now=NOW)
