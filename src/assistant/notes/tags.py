"""Tags — a per-user vocabulary of labels attached to notes (m:n).

Every user owns their own tags, and a user only ever sees the links between
notes and *their own* tags, so two collaborators on a shared note tag it
independently. Tagging is personal organization: it requires only
`view_note` on the note.

Tag names match case-insensitively after trimming (see
`normalize_tag_name`). When a note or notebook is shared, the granter's tags
on the affected notes are copied into the grantee's vocabulary by
`copy_note_tags` (called from `entitlements.grant_entitlement`).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from assistant.models.schema import NoteTag, PermissionName, Tag
from assistant.notes.exceptions import InvalidTagNameError, TagNotFoundError
from assistant.notes.permissions import require_note_access

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from assistant.models.schema import User

MAX_TAG_NAME_LENGTH = 64


def normalize_tag_name(name: str) -> tuple[str, str]:
    """Return (display name, normalized key) for a raw tag name.

    The display name is the trimmed input; the key is its casefolded form,
    used for per-user uniqueness and for matching across users on share.

    Raises:
        InvalidTagNameError: If the trimmed name is empty or longer than
            `MAX_TAG_NAME_LENGTH`.
    """
    display = name.strip()
    if not display:
        msg = "Tag name must not be empty"
        raise InvalidTagNameError(msg)
    if len(display) > MAX_TAG_NAME_LENGTH:
        msg = f"Tag name must be at most {MAX_TAG_NAME_LENGTH} characters"
        raise InvalidTagNameError(msg)
    return display, display.casefold()


def list_tags(session: Session, owner: User) -> list[Tag]:
    """Return all of `owner`'s tags, ordered by name."""
    stmt = select(Tag).where(Tag.owner_id == owner.uid).order_by(Tag.normalized_name)
    return list(session.scalars(stmt))


def _find_tag_by_key(session: Session, owner_id: uuid.UUID, key: str) -> Tag | None:
    return session.scalar(
        select(Tag).where(Tag.owner_id == owner_id, Tag.normalized_name == key),
    )


def find_or_create_tag(session: Session, owner: User, name: str) -> tuple[Tag, bool]:
    """Return `owner`'s tag matching `name`, creating it if missing.

    Returns (tag, created). Matching is case-insensitive and ignores
    surrounding whitespace. A concurrent insert of the same name is resolved
    by re-reading the row the other transaction created.
    """
    display, key = normalize_tag_name(name)
    existing = _find_tag_by_key(session, owner.uid, key)
    if existing is not None:
        return existing, False

    tag = Tag(owner_id=owner.uid, name=display, normalized_name=key)
    try:
        with session.begin_nested():
            session.add(tag)
            session.flush()
    except IntegrityError:
        existing = _find_tag_by_key(session, owner.uid, key)
        if existing is None:
            raise
        return existing, False
    return tag, True


def get_tag(session: Session, owner: User, tag_id: uuid.UUID) -> Tag:
    """Return `owner`'s tag by id.

    Raises:
        TagNotFoundError: If the tag does not exist or belongs to another
            user — the two cases are indistinguishable to the caller.
    """
    tag = session.get(Tag, tag_id)
    if tag is None or tag.owner_id != owner.uid:
        raise TagNotFoundError(str(tag_id))
    return tag


def _link(session: Session, note_id: uuid.UUID, tag_id: uuid.UUID) -> None:
    """Link a tag to a note; a no-op when the link already exists."""
    if session.get(NoteTag, (note_id, tag_id)) is None:
        session.add(NoteTag(note_id=note_id, tag_id=tag_id))


def add_tag_to_note(
    session: Session,
    caller: User,
    note_id: uuid.UUID,
    *,
    tag_id: uuid.UUID | None = None,
    name: str | None = None,
) -> Tag:
    """Tag a note with one of the caller's tags. Idempotent.

    Exactly one of `tag_id` (an existing tag) or `name` (found or created
    on the fly) must be given. Requires `view_note` on the note.

    Raises:
        ValueError: If both or neither of `tag_id`/`name` are given.
        NoteNotFoundError: If the caller cannot view the note.
        TagNotFoundError: If `tag_id` is not one of the caller's tags.
        InvalidTagNameError: If `name` is invalid.
    """
    if (tag_id is None) == (name is None):
        msg = "Exactly one of tag_id or name must be given"
        raise ValueError(msg)
    require_note_access(session, note_id, caller, PermissionName.VIEW_NOTE)
    if tag_id is not None:
        tag = get_tag(session, caller, tag_id)
    else:
        assert name is not None
        tag, _ = find_or_create_tag(session, caller, name)
    _link(session, note_id, tag.id)
    session.flush()
    return tag


def remove_tag_from_note(
    session: Session,
    caller: User,
    note_id: uuid.UUID,
    tag_id: uuid.UUID,
) -> None:
    """Remove one of the caller's tags from a note. Idempotent.

    The tag itself stays in the caller's vocabulary.

    Raises:
        NoteNotFoundError: If the caller cannot view the note.
        TagNotFoundError: If `tag_id` is not one of the caller's tags.
    """
    require_note_access(session, note_id, caller, PermissionName.VIEW_NOTE)
    get_tag(session, caller, tag_id)
    link = session.get(NoteTag, (note_id, tag_id))
    if link is not None:
        session.delete(link)
        session.flush()


def tags_for_notes(
    session: Session,
    owner: User,
    note_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, list[Tag]]:
    """Return `owner`'s tags on each of `note_ids`, ordered by name.

    Does not check note access — callers pass ids of notes they have
    already loaded through an access-checked path. Notes without tags are
    absent from the result.
    """
    if not note_ids:
        return {}
    stmt = (
        select(NoteTag.note_id, Tag)
        .join(Tag, Tag.id == NoteTag.tag_id)
        .where(Tag.owner_id == owner.uid, NoteTag.note_id.in_(note_ids))
        .order_by(Tag.normalized_name)
    )
    result: dict[uuid.UUID, list[Tag]] = defaultdict(list)
    for note_id, tag in session.execute(stmt).tuples():
        result[note_id].append(tag)
    return dict(result)


def copy_note_tags(
    session: Session,
    *,
    source: User,
    target: User,
    note_ids: Sequence[uuid.UUID],
) -> None:
    """Copy `source`'s tags on `note_ids` to `target`.

    Each of `source`'s tags is matched by name in `target`'s vocabulary,
    created there if missing, and linked to the same notes. Existing links
    are kept. Used when a note or notebook is shared, so the caller is
    responsible for `target` being able to view the notes.
    """
    if source.uid == target.uid:
        return
    target_tags: dict[str, Tag] = {}
    for note_id, tags in tags_for_notes(session, source, note_ids).items():
        for tag in tags:
            target_tag = target_tags.get(tag.normalized_name)
            if target_tag is None:
                target_tag, _ = find_or_create_tag(session, target, tag.name)
                target_tags[tag.normalized_name] = target_tag
            _link(session, note_id, target_tag.id)
    session.flush()
