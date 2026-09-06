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

Authorization
~~~~~~~~~~~~~
Every function that reads or mutates an *existing* Notebook/Note/Node takes
the acting ``User`` (never a raw id — the actor can only ever be a User) and
enforces permissions itself via ``notes/permissions.py`` (see
``docs/specs/0003_role_based_access_control.md``). Functions that only ever
act on behalf of their own creator (``create_notebook``, ``create_note``,
and the node-creation functions, which already took an ``author``) reuse
that existing parameter as the caller — no redundant second identity
parameter. Creating a Notebook or Note auto-grants its creator the matching
owner role, in the same transaction as the subject's own insert (see
``_grant_owner_entitlement``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.exc import IntegrityError

from assistant.models.schema import (
    Entitlement,
    File,
    FileState,
    MarkdownBlockType,
    Node,
    NodeType,
    Note,
    Notebook,
    PermissionName,
    RoleName,
    User,
)
from assistant.notes.exceptions import (
    DuplicateNotebookNameError,
    InvalidBlockTypeError,
    InvalidNodeTypeError,
    NodeNotFoundError,
    NodeVersionConflictError,
    NotebookNotFoundError,
    NoteNotFoundError,
)
from assistant.notes.permissions import (
    can_view_notebook,
    notebook_permissions,
    require_note_access,
    require_note_delete_access,
    require_notebook_access,
)
from assistant.notes.positions import generate_position_between

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Notebook CRUD
# ---------------------------------------------------------------------------


def _grant_owner_entitlement(
    session: Session,
    principal: User,
    role_name: RoleName,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
) -> None:
    session.add(
        Entitlement(
            principal_id=principal.uid,
            role_name=role_name.value,
            note_id=note_id,
            notebook_id=notebook_id,
        ),
    )
    session.flush()


def create_notebook(
    session: Session,
    name: str,
    owner: User,
) -> Notebook:
    notebook = Notebook(name=name, owner_id=owner.uid)
    session.add(notebook)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise DuplicateNotebookNameError(name) from None
    _grant_owner_entitlement(
        session,
        owner,
        RoleName.NOTEBOOK_OWNER,
        notebook_id=notebook.id,
    )
    return notebook


def find_or_create_notebook(
    session: Session,
    name: str,
    owner: User,
) -> Notebook:
    """Return the existing Notebook named `name`, or create one owned by owner.

    Notebook.name is globally unique, so an existing match may belong to a
    different owner than `owner` — it is returned as-is, ownership is never
    reassigned.
    """
    existing = session.scalar(select(Notebook).where(Notebook.name == name))
    if existing is not None:
        return existing
    return create_notebook(session, name, owner)


def get_notebook(
    session: Session,
    notebook_id: uuid.UUID,
    caller: User,
) -> Notebook:
    return require_notebook_access(
        session,
        notebook_id,
        caller,
        PermissionName.VIEW_NOTEBOOK,
    )


def list_notebooks(
    session: Session,
    caller: User,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[Notebook]:
    """Notebooks visible to the caller.

    Either directly (any entitlement on the notebook itself) or because the
    notebook contains at least one note the caller holds any entitlement on.
    """
    stmt = select(Notebook).where(
        or_(
            exists().where(
                Entitlement.principal_id == caller.uid,
                Entitlement.notebook_id == Notebook.id,
            ),
            exists().where(
                Entitlement.principal_id == caller.uid,
                Entitlement.note_id == Note.id,
                Note.notebook_id == Notebook.id,
            ),
        ),
    )
    stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def update_notebook(
    session: Session,
    notebook_id: uuid.UUID,
    caller: User,
    *,
    name: str | None = None,
) -> Notebook:
    notebook = require_notebook_access(
        session,
        notebook_id,
        caller,
        PermissionName.UPDATE_NOTEBOOK,
    )
    if name is not None:
        notebook.name = name
    session.flush()
    return notebook


def delete_notebook(
    session: Session,
    notebook_id: uuid.UUID,
    caller: User,
) -> None:
    notebook = require_notebook_access(
        session,
        notebook_id,
        caller,
        PermissionName.DELETE_NOTEBOOK,
    )
    session.delete(notebook)
    session.flush()


# ---------------------------------------------------------------------------
# Note CRUD
# ---------------------------------------------------------------------------


def create_note(
    session: Session,
    notebook_id: uuid.UUID,
    owner: User,
    title: str,
    *,
    external_id: str | None = None,
) -> Note:
    require_notebook_access(session, notebook_id, owner, PermissionName.CREATE_NOTES)
    note = Note(
        notebook_id=notebook_id,
        owner_id=owner.uid,
        title=title,
        external_id=external_id,
        update_timestamp=datetime.now(UTC),
    )
    session.add(note)
    session.flush()
    _grant_owner_entitlement(session, owner, RoleName.NOTE_OWNER, note_id=note.id)
    return note


def get_note(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
) -> Note:
    return require_note_access(session, note_id, caller, PermissionName.VIEW_NOTE)


def list_notes(
    session: Session,
    notebook_id: uuid.UUID,
    caller: User,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[Note]:
    """Notes visible to the caller in this notebook.

    All notes, if the caller holds LIST_NOTES/VIEW_NOTES/OWN_NOTES on the
    notebook; otherwise only the notes the caller holds a direct
    entitlement on.

    Visibility here is `can_view_notebook` (which also covers "I can see
    this notebook only because I hold an entitlement on one note inside
    it"), not a `VIEW_NOTEBOOK` permission check — sharing a single note
    must not require also granting a notebook-level permission.
    """
    if not can_view_notebook(session, caller, notebook_id):
        raise NotebookNotFoundError(str(notebook_id))
    perms = notebook_permissions(session, caller, notebook_id)
    listable = {
        PermissionName.LIST_NOTES,
        PermissionName.VIEW_NOTES,
        PermissionName.OWN_NOTES,
    }
    if perms & listable:
        stmt = select(Note).where(Note.notebook_id == notebook_id)
    else:
        stmt = select(Note).where(
            Note.notebook_id == notebook_id,
            exists().where(
                Entitlement.principal_id == caller.uid,
                Entitlement.note_id == Note.id,
            ),
        )
    stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def update_note(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
    *,
    title: str | None = None,
) -> Note:
    note = require_note_access(session, note_id, caller, PermissionName.UPDATE)
    if title is not None:
        note.title = title
    _touch_note(session, note_id)
    session.flush()
    return note


def delete_note(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
) -> None:
    note = require_note_delete_access(session, note_id, caller)
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


def _require_node_and_note_update_access(
    session: Session,
    node_id: uuid.UUID,
    caller: User,
) -> Node:
    """Fetch a node by id (404 if absent) and require note UPDATE on its parent."""
    node = session.get(Node, node_id)
    if node is None:
        raise NodeNotFoundError(str(node_id))
    require_note_access(session, node.note_id, caller, PermissionName.UPDATE)
    return node


def get_ordered_nodes(
    session: Session,
    note_id: uuid.UUID,
    caller: User,
) -> list[Node]:
    """Return all nodes for a note, sorted by position."""
    require_note_access(session, note_id, caller, PermissionName.VIEW_NOTE)
    stmt = select(Node).where(Node.note_id == note_id).order_by(Node.position)
    return list(session.scalars(stmt))


def validate_note_in_notebook(
    session: Session,
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
) -> None:
    """Confirm a note exists and belongs to the given notebook.

    No permission check — this only guards against a note_id that doesn't
    belong under this notebook_id, a URL-scoping concern for nested routes.
    Callers must separately invoke a permission-checked function (e.g.
    `get_ordered_nodes`, `add_text_node`) to authorize the actual request.
    """
    note = session.get(Note, note_id)
    if note is None or note.notebook_id != notebook_id:
        raise NoteNotFoundError(str(note_id))


def get_node_in_note(
    session: Session,
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    node_id: uuid.UUID,
) -> Node:
    """Resolve a node scoped to (notebook_id, note_id). No permission check —
    see `validate_note_in_notebook`.
    """
    validate_note_in_notebook(session, notebook_id, note_id)
    node = session.get(Node, node_id)
    if node is None or node.note_id != note_id:
        raise NodeNotFoundError(str(node_id))
    return node


def validate_node_in_note(
    session: Session,
    note_id: uuid.UUID,
    node_id: uuid.UUID,
) -> None:
    """Confirm a node exists and belongs to the given note. No permission check."""
    node = session.get(Node, node_id)
    if node is None or node.note_id != note_id:
        raise NodeNotFoundError(str(node_id))


def get_note_by_external_id(
    session: Session,
    notebook_id: uuid.UUID,
    external_id: str,
) -> Note | None:
    """Look up a Note by its (notebook_id, external_id) dedup key. None if absent."""
    return session.scalar(
        select(Note).where(
            Note.notebook_id == notebook_id,
            Note.external_id == external_id,
        ),
    )


# ---------------------------------------------------------------------------
# Node operations
# ---------------------------------------------------------------------------


def add_text_node(
    session: Session,
    note_id: uuid.UUID,
    author: User,
    payload: str,
) -> Node:
    """Append a text node at the end of a note's content list."""
    require_note_access(session, note_id, author, PermissionName.UPDATE)
    last = _last_position(session, note_id, lock=True)
    position = generate_position_between(last, None)
    node = Node(
        note_id=note_id,
        position=position,
        author_id=author.uid,
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
    author: User,
    file_id: uuid.UUID,
) -> Node:
    """Append an attachment node at the end of a note's content list.

    The file must be complete and must belong to the given note. The node
    payload is a pre-formatted markdown link so the editor can render it
    without special handling.

    Raises:
        ValueError: If the file is not found, not complete, or belongs to a
            different note.
    """
    require_note_access(session, note_id, author, PermissionName.UPDATE)
    file = session.get(File, file_id)
    if file is None:
        msg = f"File not found: {file_id}"
        raise ValueError(msg)
    if file.state != FileState.COMPLETE.value:
        msg = f"File {file_id} is not complete (state={file.state})"
        raise ValueError(msg)
    if file.note_id != note_id:
        msg = f"File {file_id} does not belong to note {note_id}"
        raise ValueError(msg)

    payload = f"[{file.file_name}](/files/{file_id})"
    last = _last_position(session, note_id, lock=True)
    position = generate_position_between(last, None)
    node = Node(
        note_id=note_id,
        position=position,
        author_id=author.uid,
        node_type=NodeType.ATTACHMENT,
        attachment_id=file_id,
        payload=payload,
    )
    session.add(node)
    _touch_note(session, note_id)
    session.flush()
    return node


def insert_text_node(  # noqa: PLR0913
    session: Session,
    note_id: uuid.UUID,
    author: User,
    payload: str,
    after_node_id: uuid.UUID | None = None,
    before_node_id: uuid.UUID | None = None,
) -> Node:
    """Insert a text node between two existing nodes.

    A new position is generated between the neighbours so the
    surrounding nodes are unaffected. At least one of *after_node_id*
    or *before_node_id* must be provided.
    """
    require_note_access(session, note_id, author, PermissionName.UPDATE)
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
        author_id=author.uid,
        node_type=NodeType.TEXT,
        payload=payload,
    )
    session.add(node)
    _touch_note(session, note_id)
    session.flush()
    return node


# ---------------------------------------------------------------------------
# Markdown node operations
# ---------------------------------------------------------------------------


def _validate_block_type(block_type: str) -> MarkdownBlockType:
    try:
        return MarkdownBlockType(block_type)
    except ValueError:
        valid = ", ".join(bt.value for bt in MarkdownBlockType)
        msg = f"Invalid block type '{block_type}'. Must be one of: {valid}"
        raise InvalidBlockTypeError(msg) from None


def _ensure_markdown_node(node: Node) -> None:
    if node.node_type != NodeType.MARKDOWN:
        msg = f"Node {node.id} is {node.node_type}, expected markdown"
        raise InvalidNodeTypeError(msg)


def add_markdown_node(
    session: Session,
    note_id: uuid.UUID,
    author: User,
    payload: str,
    block_type: str,
) -> Node:
    """Append a markdown node at the end of a note's content list."""
    require_note_access(session, note_id, author, PermissionName.UPDATE)
    validated_bt = _validate_block_type(block_type)
    last = _last_position(session, note_id, lock=True)
    position = generate_position_between(last, None)
    node = Node(
        note_id=note_id,
        position=position,
        author_id=author.uid,
        node_type=NodeType.MARKDOWN,
        payload=payload,
        block_type=validated_bt.value,
    )
    session.add(node)
    _touch_note(session, note_id)
    session.flush()
    return node


def insert_markdown_node(  # noqa: PLR0913
    session: Session,
    note_id: uuid.UUID,
    author: User,
    payload: str,
    block_type: str,
    after_node_id: uuid.UUID | None = None,
    before_node_id: uuid.UUID | None = None,
) -> Node:
    """Insert a markdown node between two existing nodes.

    At least one of *after_node_id* or *before_node_id* must be provided.
    """
    require_note_access(session, note_id, author, PermissionName.UPDATE)
    validated_bt = _validate_block_type(block_type)
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
        author_id=author.uid,
        node_type=NodeType.MARKDOWN,
        payload=payload,
        block_type=validated_bt.value,
    )
    session.add(node)
    _touch_note(session, note_id)
    session.flush()
    return node


def update_markdown_node(  # noqa: PLR0913
    session: Session,
    node_id: uuid.UUID,
    caller: User,
    payload: str,
    block_type: str,
    expected_version: int,
) -> Node:
    """Update a markdown node's payload and block type.

    Uses the same optimistic locking as ``update_text_node``.
    """
    node = _require_node_and_note_update_access(session, node_id, caller)
    validated_bt = _validate_block_type(block_type)
    _ensure_markdown_node(node)
    stmt = (
        update(Node)
        .where(Node.id == node_id, Node.version == expected_version)
        .values(
            payload=payload,
            block_type=validated_bt.value,
            version=Node.version + 1,
            update_timestamp=datetime.now(UTC),
        )
    )
    rowcount: int = session.execute(stmt).rowcount  # type: ignore[attr-defined]
    if rowcount == 0:
        session.expire(node)
        raise NodeVersionConflictError(
            node_id,
            expected_version,
            node.version,
        )
    session.expire_all()
    refreshed = session.get(Node, node_id)
    assert refreshed is not None
    _touch_note(session, refreshed.note_id)
    session.flush()
    return refreshed


def update_text_node(
    session: Session,
    node_id: uuid.UUID,
    caller: User,
    payload: str,
    expected_version: int,
) -> Node:
    """Replace the text content of a node.

    Uses optimistic locking: the update only succeeds when the node's
    current version matches *expected_version*. On success the version
    is incremented. On mismatch a ``NodeVersionConflictError`` is
    raised containing the current version so the caller can retry.
    """
    _require_node_and_note_update_access(session, node_id, caller)
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
    author: User,
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
    node = _require_node_and_note_update_access(session, node_id, author)
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
        author_id=author.uid,
        node_type=NodeType.TEXT,
        payload=right_payload,
    )
    session.add(new_node)
    _touch_note(session, node.note_id)
    session.flush()
    return node, new_node


def merge_text_nodes(  # noqa: PLR0913
    session: Session,
    node_id: uuid.UUID,
    caller: User,
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
    source = _require_node_and_note_update_access(session, node_id, caller)
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


def replace_markdown_nodes(
    session: Session,
    note_id: uuid.UUID,
    author: User,
    blocks: list[tuple[str, str]],
) -> list[Node]:
    """Delete all of a note's existing nodes and recreate them from `blocks`.

    `blocks` is a list of (block_type, payload) pairs, in order. Each
    recreated node touches the note itself via `add_markdown_node`; if
    `blocks` is empty, no nodes are created so the note is touched directly
    here instead.
    """
    require_note_access(session, note_id, author, PermissionName.UPDATE)
    session.execute(delete(Node).where(Node.note_id == note_id))
    if not blocks:
        _touch_note(session, note_id)
        session.flush()
        return []
    return [
        add_markdown_node(session, note_id, author, payload, block_type)
        for block_type, payload in blocks
    ]


def delete_node(
    session: Session,
    node_id: uuid.UUID,
    caller: User,
) -> uuid.UUID | None:
    """Remove a node from its note. Idempotent — deleting an absent node is a no-op.

    Returns the id of the node's attachment file, for an attachment node —
    None otherwise (including when the node didn't exist), so callers can
    clean up the associated file record without a separate lookup.
    """
    node = session.get(Node, node_id)
    if node is None:
        return None
    require_note_access(session, node.note_id, caller, PermissionName.UPDATE)
    attachment_id = node.attachment_id if node.node_type == NodeType.ATTACHMENT else None
    note_id = node.note_id
    session.delete(node)
    _touch_note(session, note_id)
    session.flush()
    return attachment_id
