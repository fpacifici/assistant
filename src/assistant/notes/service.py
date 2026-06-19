"""Notes service — Notebook/Note CRUD and Node operations.

Data Model
----------
A **User** owns **Notebooks**, and each Notebook contains **Notes**.
A Note is composed of an ordered list of **Nodes**. Each Node holds one
chunk of content — either text (``node_type="text"``, content in
``payload``) or an attachment reference (``node_type="attachment"``,
reference in ``attachment_id``).

Node Ordering
~~~~~~~~~~~~~
Nodes are sorted by a ``position`` column that uses fractional indexing:
short, lexicographically sortable strings. Between any two positions a
new one can always be generated, so inserting a Node never requires
renumbering existing ones. Retrieving a Note's content is a single
query ordered by ``position``.

Example — a note with three text nodes::

    position  payload
    --------  --------------------------
    "V"       "This is a paragraph"
    "VV"      "This is the second one"
    "d"       "This is the third one"

Concurrent Editing
~~~~~~~~~~~~~~~~~~
Every Node carries a ``version`` integer (starting at 1). When a client
updates a node it sends the version it last read. The update succeeds
only if the version still matches; otherwise the caller receives a
conflict error with the current state so the user can re-apply their
edit. This is optimistic locking — no long-held locks, and two users
editing *different* nodes in the same note never conflict.

Split & Merge
~~~~~~~~~~~~~
**Split** divides a text node at a character offset. The original node
keeps the left portion and a new node is created for the right portion,
with a position generated between the original and its next neighbour.
Both the original's version and the Note's timestamp are bumped.

Example — splitting the second node at offset 12::

    Before                          After
    ------                          -----
    "V"   "A paragraph"             "V"   "A paragraph"
    "VV"  "This is the second one"  "VV"  "This is the" (version 2)
                                    "Vd"  " second one" (version 1, new)
    "d"   "Third one"               "d"   "Third one"

**Merge** absorbs one text node into another. The target node's payload
is extended with the source's payload, the source is deleted, and the
target's version is bumped.

Example — merging the second node into the first::

    Before                  After
    ------                  -----
    "V"   "A paragraph"     "V"   "A paragraphSecond" (version 2)
    "VV"  "Second"          (deleted)
    "d"   "Third"           "d"   "Third"
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from assistant.models.schema import (
    AttachmentMetadata,
    Node,
    NodeType,
    Note,
    Notebook,
)
from assistant.notes.exceptions import (
    InvalidNodeTypeError,
    NodeNotFoundError,
    NodeVersionConflictError,
    NotebookNotFoundError,
    NoteNotFoundError,
)
from assistant.notes.positions import generate_position_between

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Notebook CRUD
# ---------------------------------------------------------------------------


def create_notebook(
    session: Session,
    name: str,
    owner_id: uuid.UUID,
) -> Notebook:
    notebook = Notebook(name=name, owner_id=owner_id)
    session.add(notebook)
    session.flush()
    return notebook


def get_notebook(
    session: Session,
    notebook_id: uuid.UUID,
) -> Notebook:
    notebook = session.get(Notebook, notebook_id)
    if notebook is None:
        raise NotebookNotFoundError(str(notebook_id))
    return notebook


def list_notebooks(
    session: Session,
    owner_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[Notebook]:
    stmt = select(Notebook).where(Notebook.owner_id == owner_id).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def update_notebook(
    session: Session,
    notebook_id: uuid.UUID,
    *,
    name: str | None = None,
) -> Notebook:
    notebook = get_notebook(session, notebook_id)
    if name is not None:
        notebook.name = name
    session.flush()
    return notebook


def delete_notebook(
    session: Session,
    notebook_id: uuid.UUID,
) -> None:
    notebook = get_notebook(session, notebook_id)
    session.delete(notebook)
    session.flush()


# ---------------------------------------------------------------------------
# Note CRUD
# ---------------------------------------------------------------------------


def create_note(
    session: Session,
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
) -> Note:
    note = Note(
        notebook_id=notebook_id,
        owner_id=owner_id,
        title=title,
        update_timestamp=datetime.now(UTC),
    )
    session.add(note)
    session.flush()
    return note


def get_note(
    session: Session,
    note_id: uuid.UUID,
) -> Note:
    note = session.get(Note, note_id)
    if note is None:
        raise NoteNotFoundError(str(note_id))
    return note


def list_notes(
    session: Session,
    notebook_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[Note]:
    stmt = select(Note).where(Note.notebook_id == notebook_id).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def update_note(
    session: Session,
    note_id: uuid.UUID,
    *,
    title: str | None = None,
) -> Note:
    note = get_note(session, note_id)
    if title is not None:
        note.title = title
    _touch_note(session, note_id)
    session.flush()
    return note


def delete_note(
    session: Session,
    note_id: uuid.UUID,
) -> None:
    note = get_note(session, note_id)
    session.delete(note)
    session.flush()


def _ensure_text_node(node: Node) -> None:
    if node.node_type != NodeType.TEXT:
        msg = f"Node {node.id} is {node.node_type}, expected text"
        raise InvalidNodeTypeError(msg)


def _touch_note(session: Session, note_id: uuid.UUID) -> None:
    session.execute(
        update(Note).where(Note.id == note_id).values(update_timestamp=datetime.now(UTC)),
    )


def _last_position(
    session: Session,
    note_id: uuid.UUID,
    *,
    lock: bool = False,
) -> str | None:
    stmt = (
        select(Node.position)
        .where(Node.note_id == note_id)
        .order_by(Node.position.desc())
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    return session.scalar(stmt)


def get_ordered_nodes(
    session: Session,
    note_id: uuid.UUID,
) -> list[Node]:
    """Return all nodes for a note, sorted by position."""
    stmt = select(Node).where(Node.note_id == note_id).order_by(Node.position)
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------


def add_text_node(
    session: Session,
    note_id: uuid.UUID,
    author_id: uuid.UUID,
    payload: str,
) -> Node:
    """Append a text node at the end of a note's content list."""
    last = _last_position(session, note_id, lock=True)
    position = generate_position_between(last, None)
    node = Node(
        note_id=note_id,
        position=position,
        author_id=author_id,
        node_type=NodeType.TEXT,
        payload=payload,
    )
    session.add(node)
    _touch_note(session, note_id)
    session.flush()
    return node


def add_attachment_node(
    session: Session,
    note_id: uuid.UUID,
    author_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> Node:
    """Append an attachment node at the end of a note's content list."""
    session.get(AttachmentMetadata, attachment_id)
    last = _last_position(session, note_id, lock=True)
    position = generate_position_between(last, None)
    node = Node(
        note_id=note_id,
        position=position,
        author_id=author_id,
        node_type=NodeType.ATTACHMENT,
        attachment_id=attachment_id,
    )
    session.add(node)
    _touch_note(session, note_id)
    session.flush()
    return node


def insert_text_node(  # noqa: PLR0913
    session: Session,
    note_id: uuid.UUID,
    author_id: uuid.UUID,
    payload: str,
    after_node_id: uuid.UUID | None = None,
    before_node_id: uuid.UUID | None = None,
) -> Node:
    """Insert a text node between two existing nodes.

    A new position is generated between the neighbours so the
    surrounding nodes are unaffected. At least one of *after_node_id*
    or *before_node_id* must be provided.
    """
    before_pos: str | None = None
    after_pos: str | None = None

    if after_node_id is not None:
        after_node = session.execute(
            select(Node).where(Node.id == after_node_id).with_for_update(),
        ).scalar_one_or_none()
        if after_node is None:
            raise NodeNotFoundError(str(after_node_id))
        after_pos = after_node.position

    if before_node_id is not None:
        before_node = session.execute(
            select(Node).where(Node.id == before_node_id).with_for_update(),
        ).scalar_one_or_none()
        if before_node is None:
            raise NodeNotFoundError(str(before_node_id))
        before_pos = before_node.position

    position = generate_position_between(after_pos, before_pos)
    node = Node(
        note_id=note_id,
        position=position,
        author_id=author_id,
        node_type=NodeType.TEXT,
        payload=payload,
    )
    session.add(node)
    _touch_note(session, note_id)
    session.flush()
    return node


def update_text_node(
    session: Session,
    node_id: uuid.UUID,
    payload: str,
    expected_version: int,
) -> Node:
    """Replace the text content of a node.

    Uses optimistic locking: the update only succeeds when the node's
    current version matches *expected_version*. On success the version
    is incremented. On mismatch a ``NodeVersionConflictError`` is
    raised containing the current version so the caller can retry.
    """
    stmt = (
        update(Node)
        .where(Node.id == node_id, Node.version == expected_version)
        .values(
            payload=payload,
            version=Node.version + 1,
            update_timestamp=datetime.now(UTC),
        )
    )
    rowcount: int = session.execute(stmt).rowcount  # type: ignore[attr-defined]
    if rowcount == 0:
        node = session.get(Node, node_id)
        if node is None:
            raise NodeNotFoundError(str(node_id))
        raise NodeVersionConflictError(
            node_id,
            expected_version,
            node.version,
        )
    session.expire_all()
    node = session.get(Node, node_id)
    assert node is not None
    _touch_note(session, node.note_id)
    session.flush()
    return node


def split_text_node(
    session: Session,
    node_id: uuid.UUID,
    author_id: uuid.UUID,
    split_offset: int,
    expected_version: int,
) -> tuple[Node, Node]:
    """Split a text node at a character offset.

    The original node keeps ``payload[:split_offset]`` and its position.
    A new node is created with ``payload[split_offset:]`` at a position
    between the original and its next neighbour. The original node's
    version is bumped; the new node starts at version 1.

    Returns the (original, new) node pair.
    """
    node = session.get(Node, node_id)
    if node is None:
        raise NodeNotFoundError(str(node_id))
    _ensure_text_node(node)
    if node.version != expected_version:
        raise NodeVersionConflictError(
            node_id,
            expected_version,
            node.version,
        )

    original_payload = node.payload or ""
    left_payload = original_payload[:split_offset]
    right_payload = original_payload[split_offset:]

    # Find next position after this node.
    stmt = (
        select(Node.position)
        .where(Node.note_id == node.note_id, Node.position > node.position)
        .order_by(Node.position)
        .limit(1)
    )
    next_pos = session.scalar(stmt)
    new_position = generate_position_between(node.position, next_pos)

    node.payload = left_payload
    node.version += 1
    node.update_timestamp = datetime.now(UTC)

    new_node = Node(
        note_id=node.note_id,
        position=new_position,
        author_id=author_id,
        node_type=NodeType.TEXT,
        payload=right_payload,
    )
    session.add(new_node)
    _touch_note(session, node.note_id)
    session.flush()
    return node, new_node


def merge_text_nodes(
    session: Session,
    node_id: uuid.UUID,
    merge_into_id: uuid.UUID,
    expected_version_node: int,
    expected_version_target: int,
) -> Node:
    """Merge one text node into another.

    The target node (*merge_into_id*) absorbs the source node's
    (*node_id*) payload by appending it. The source node is deleted
    and the target's version is bumped. The target keeps its original
    position.
    """
    source = session.get(Node, node_id)
    if source is None:
        raise NodeNotFoundError(str(node_id))
    _ensure_text_node(source)
    if source.version != expected_version_node:
        raise NodeVersionConflictError(
            node_id,
            expected_version_node,
            source.version,
        )

    target = session.get(Node, merge_into_id)
    if target is None:
        raise NodeNotFoundError(str(merge_into_id))
    _ensure_text_node(target)
    if target.version != expected_version_target:
        raise NodeVersionConflictError(
            merge_into_id,
            expected_version_target,
            target.version,
        )

    target.payload = (target.payload or "") + (source.payload or "")
    target.version += 1
    target.update_timestamp = datetime.now(UTC)
    session.delete(source)
    _touch_note(session, target.note_id)
    session.flush()
    return target


def delete_node(
    session: Session,
    node_id: uuid.UUID,
) -> None:
    """Remove a node from its note. Idempotent — deleting an absent node is a no-op."""
    node = session.get(Node, node_id)
    if node is None:
        return
    note_id = node.note_id
    session.delete(node)
    _touch_note(session, note_id)
    session.flush()
