"""Who has a note open, where their cursor is, and what changed since.

A browser tab with a note open beats every few seconds (`heartbeat`); a tab
that stops beating for `PRESENCE_TTL` is no longer active, and its row is
deleted by a later heartbeat. `leave` removes it right away.

The open note polls `live_state`: the note's revision (its
`update_timestamp`, which every content change bumps through
`service._touch_note`), its nodes when the revision is not the one the
client holds, and the other users active on it. The client merges the nodes
into its editor (`frontend/src/markdown/liveMerge.ts`).

Presence is per tab (`client_id`), shown per user: lists hold each other
user once, with their most recent cursor, and never the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from assistant.models.schema import Note, NotePresence, PermissionName, User
from assistant.notes.exceptions import NotebookNotFoundError, PresenceClientTakenError
from assistant.notes.permissions import (
    can_view_notebook,
    require_note_access,
    viewable_note_filter,
)
from assistant.notes.service import get_ordered_nodes

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from sqlalchemy.orm import Session

    from assistant.models.schema import Node

PRESENCE_TTL = timedelta(seconds=30)
"""Three missed heartbeats (the client beats every 10 s)."""


@dataclass(frozen=True, slots=True)
class Cursor:
    """A caret: the node holding it and the character offset in that node."""

    node_id: uuid.UUID
    offset: int


@dataclass(frozen=True, slots=True)
class ActiveUser:
    """Another user with the note open."""

    user_id: uuid.UUID
    name: str
    initial: str
    cursor: Cursor | None


@dataclass(frozen=True, slots=True)
class NotePresenceEntry:
    """The other users active on one note of a notebook."""

    note_id: uuid.UUID
    users: list[ActiveUser]


@dataclass(frozen=True, slots=True)
class LiveNote:
    """What an open note polls for.

    `nodes` is None when the client already holds `revision`.
    """

    revision: str
    title: str
    nodes: list[Node] | None
    presence: list[ActiveUser]


def _now() -> datetime:
    return datetime.now(UTC)


def heartbeat(  # noqa: PLR0913
    session: Session,
    note_id: uuid.UUID,
    caller: User,
    client_id: uuid.UUID,
    cursor: Cursor | None,
    *,
    now: datetime | None = None,
) -> None:
    """Record that the caller's tab `client_id` has the note open.

    Needs `view_note`. Also deletes every presence that expired, on any note.

    Raises:
        NoteNotFoundError: The caller cannot view the note.
        PresenceClientTakenError: Another user holds `client_id` on this note.
    """
    require_note_access(session, note_id, caller, PermissionName.VIEW_NOTE)
    now = now or _now()
    session.execute(
        delete(NotePresence).where(NotePresence.last_seen < now - PRESENCE_TTL)
    )

    row = session.get(NotePresence, (note_id, client_id))
    if row is None:
        row = NotePresence(note_id=note_id, client_id=client_id, user_id=caller.uid)
        _apply(row, cursor, now)
        try:
            # Two beats of one tab can race (the timer and a cursor move).
            with session.begin_nested():
                session.add(row)
        except IntegrityError:
            row = session.get(NotePresence, (note_id, client_id))
            if row is None:  # pragma: no cover - deleted in between
                raise
        else:
            return
    if row.user_id != caller.uid:
        raise PresenceClientTakenError(client_id)
    _apply(row, cursor, now)
    session.flush()


def _apply(row: NotePresence, cursor: Cursor | None, now: datetime) -> None:
    row.cursor_node_id = cursor.node_id if cursor else None
    row.cursor_offset = cursor.offset if cursor else None
    row.last_seen = now


def leave(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
    client_id: uuid.UUID,
) -> None:
    """Forget the caller's tab `client_id` on the note. Idempotent.

    Needs no permission: it only ever deletes the caller's own row, so it
    still works after the caller lost access to the note.
    """
    session.execute(
        delete(NotePresence).where(
            NotePresence.note_id == note_id,
            NotePresence.client_id == client_id,
            NotePresence.user_id == caller.uid,
        ),
    )


def _display_name(user: User) -> str:
    name = f"{user.firstname} {user.lastname}".strip()
    return name or user.email


def _initial(user: User) -> str:
    source = user.firstname.strip() or user.email
    return source[:1].upper()


def _per_user(rows: Iterable[tuple[NotePresence, User]]) -> list[ActiveUser]:
    """One entry per user, from rows sorted most recent first."""
    seen: set[uuid.UUID] = set()
    users: list[ActiveUser] = []
    for presence, user in rows:
        if user.uid in seen:
            continue
        seen.add(user.uid)
        cursor = (
            Cursor(presence.cursor_node_id, presence.cursor_offset)
            if presence.cursor_node_id is not None and presence.cursor_offset is not None
            else None
        )
        users.append(
            ActiveUser(
                user_id=user.uid,
                name=_display_name(user),
                initial=_initial(user),
                cursor=cursor,
            ),
        )
    return users


def active_on_note(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
    *,
    now: datetime | None = None,
) -> list[ActiveUser]:
    """The other users with the note open. Needs `view_note`."""
    require_note_access(session, note_id, caller, PermissionName.VIEW_NOTE)
    return _active_on_note(session, note_id, caller, now or _now())


def _active_on_note(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
    now: datetime,
) -> list[ActiveUser]:
    stmt = (
        select(NotePresence, User)
        .join(User, User.uid == NotePresence.user_id)
        .where(
            NotePresence.note_id == note_id,
            NotePresence.user_id != caller.uid,
            NotePresence.last_seen >= now - PRESENCE_TTL,
        )
        .order_by(NotePresence.last_seen.desc())
    )
    return _per_user(session.execute(stmt).tuples())


def active_in_notebook(
    session: Session,
    notebook_id: uuid.UUID,
    caller: User,
    *,
    now: datetime | None = None,
) -> list[NotePresenceEntry]:
    """For each note of the notebook the caller can view, the other users on it.

    Notes nobody else has open are left out.

    Raises:
        NotebookNotFoundError: The caller cannot view the notebook.
    """
    if not can_view_notebook(session, caller, notebook_id):
        raise NotebookNotFoundError(str(notebook_id))
    now = now or _now()
    stmt = (
        select(NotePresence, User)
        .join(User, User.uid == NotePresence.user_id)
        .join(Note, Note.id == NotePresence.note_id)
        .where(
            Note.notebook_id == notebook_id,
            viewable_note_filter(caller),
            NotePresence.user_id != caller.uid,
            NotePresence.last_seen >= now - PRESENCE_TTL,
        )
        .order_by(NotePresence.last_seen.desc())
    )
    by_note: dict[uuid.UUID, list[tuple[NotePresence, User]]] = {}
    for presence, user in session.execute(stmt).tuples():
        by_note.setdefault(presence.note_id, []).append((presence, user))
    return [
        NotePresenceEntry(note_id=note_id, users=_per_user(rows))
        for note_id, rows in by_note.items()
    ]


def note_revision(note: Note) -> str:
    """The token that changes whenever the note's content or title changes."""
    return note.update_timestamp.isoformat()


def live_state(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
    since: str | None,
    *,
    now: datetime | None = None,
) -> LiveNote:
    """The note's revision, its nodes unless the client holds `since`, and who is on it.

    The revision is compared for difference, not order: a change can't be
    missed when two commits land out of timestamp order.

    Raises:
        NoteNotFoundError: The caller cannot view the note.
    """
    note = require_note_access(session, note_id, caller, PermissionName.VIEW_NOTE)
    revision = note_revision(note)
    nodes = get_ordered_nodes(session, note_id, caller) if since != revision else None
    return LiveNote(
        revision=revision,
        title=note.title,
        nodes=nodes,
        presence=_active_on_note(session, note_id, caller, now or _now()),
    )
