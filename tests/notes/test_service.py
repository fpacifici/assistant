"""Tests for the Notes service module."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import assistant.notes.service as service_module
from assistant.models.schema import (
    Entitlement,
    File,
    FileState,
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
    PermissionDeniedError,
)
from assistant.notes.service import (
    add_attachment_node,
    add_markdown_node,
    add_text_node,
    create_note,
    create_notebook,
    delete_node,
    delete_note,
    delete_notebook,
    find_or_create_notebook,
    get_node_in_note,
    get_note,
    get_note_by_external_id,
    get_notebook,
    get_ordered_nodes,
    insert_markdown_node,
    insert_text_node,
    list_notebooks,
    list_notes,
    merge_text_nodes,
    replace_markdown_nodes,
    split_text_node,
    update_markdown_node,
    update_note,
    update_notebook,
    update_text_node,
    validate_node_in_note,
    validate_note_in_notebook,
)


def _make_user(session: Session, email: str = "u@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


# -----------------------------------------------------------------------
# Notebook CRUD
# -----------------------------------------------------------------------


def test_create_notebook(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    assert nb.id is not None
    assert nb.name == "Work"
    assert nb.owner_id == user.uid


def test_get_notebook(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    fetched = get_notebook(db_session, nb.id, user)
    assert fetched.id == nb.id


def test_get_notebook_not_found(db_session: Session) -> None:
    user = _make_user(db_session)
    with pytest.raises(NotebookNotFoundError):
        get_notebook(db_session, uuid.uuid4(), user)


def test_list_notebooks_filters_by_owner(db_session: Session) -> None:
    u1 = _make_user(db_session, "a@test.com")
    u2 = _make_user(db_session, "b@test.com")
    create_notebook(db_session, "NB1", u1)
    create_notebook(db_session, "NB2", u1)
    create_notebook(db_session, "NB3", u2)

    assert len(list_notebooks(db_session, u1)) == 2
    assert len(list_notebooks(db_session, u2)) == 1


def test_delete_notebook_cascades(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "Note")
    add_text_node(db_session, note.id, user, "content")

    delete_notebook(db_session, nb.id, user)

    assert db_session.query(Note).count() == 0
    assert db_session.query(Node).count() == 0


def test_delete_notebook_not_found(db_session: Session) -> None:
    user = _make_user(db_session)
    with pytest.raises(NotebookNotFoundError):
        delete_notebook(db_session, uuid.uuid4(), user)


def test_create_notebook_duplicate_name_raises(db_session: Session) -> None:
    user = _make_user(db_session)
    create_notebook(db_session, "Work", user)

    with pytest.raises(DuplicateNotebookNameError):
        create_notebook(db_session, "Work", user)


def test_find_or_create_notebook_creates_when_absent(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = find_or_create_notebook(db_session, "Personal", user)
    assert nb.name == "Personal"
    assert nb.owner_id == user.uid


def test_find_or_create_notebook_returns_existing(db_session: Session) -> None:
    user = _make_user(db_session)
    created = create_notebook(db_session, "Personal", user)

    found = find_or_create_notebook(db_session, "Personal", user)
    assert found.id == created.id


def test_find_or_create_notebook_returns_existing_regardless_of_owner(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    created = create_notebook(db_session, "Shared", owner)

    found = find_or_create_notebook(db_session, "Shared", other)
    assert found.id == created.id
    assert found.owner_id == owner.uid


# -----------------------------------------------------------------------
# Note CRUD
# -----------------------------------------------------------------------


def test_create_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "My Note")

    assert note.id is not None
    assert note.title == "My Note"
    assert note.creation_timestamp is not None
    assert note.update_timestamp is not None


def test_get_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "Note")
    fetched = get_note(db_session, note.id, user)
    assert fetched.id == note.id


def test_get_note_not_found(db_session: Session) -> None:
    user = _make_user(db_session)
    with pytest.raises(NoteNotFoundError):
        get_note(db_session, uuid.uuid4(), user)


def test_list_notes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    create_note(db_session, nb.id, user, "Note 1")
    create_note(db_session, nb.id, user, "Note 2")

    assert len(list_notes(db_session, nb.id, user)) == 2


def test_create_note_with_external_id(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "My Note", external_id="abc123")

    assert note.external_id == "abc123"


def test_create_note_without_external_id_defaults_to_none(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "My Note")

    assert note.external_id is None


def test_get_note_by_external_id_found(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "My Note", external_id="abc123")

    found = get_note_by_external_id(db_session, nb.id, "abc123")
    assert found is not None
    assert found.id == note.id


def test_get_note_by_external_id_not_found(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)

    assert get_note_by_external_id(db_session, nb.id, "missing") is None


def test_get_note_by_external_id_scoped_per_notebook(db_session: Session) -> None:
    user = _make_user(db_session)
    nb1 = create_notebook(db_session, "Work", user)
    nb2 = create_notebook(db_session, "Personal", user)
    create_note(db_session, nb1.id, user, "Note", external_id="same-hash")

    assert get_note_by_external_id(db_session, nb2.id, "same-hash") is None


def test_delete_note_cascades_nodes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "Note")
    add_text_node(db_session, note.id, user, "p1")
    add_text_node(db_session, note.id, user, "p2")

    delete_note(db_session, note.id, user)
    assert db_session.query(Node).count() == 0


# -----------------------------------------------------------------------
# Node operations — add / insert
# -----------------------------------------------------------------------


def test_add_text_node_to_empty_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    node = add_text_node(db_session, note.id, user, "Hello")
    assert node.payload == "Hello"
    assert node.node_type == NodeType.TEXT
    assert node.version == 1
    assert node.position is not None


def test_add_text_nodes_append_in_order(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    n1 = add_text_node(db_session, note.id, user, "first")
    n2 = add_text_node(db_session, note.id, user, "second")
    n3 = add_text_node(db_session, note.id, user, "third")

    assert n1.position < n2.position < n3.position
    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [n.payload for n in nodes] == ["first", "second", "third"]


def test_add_attachment_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()

    node = add_attachment_node(db_session, note.id, user, file.id)
    assert node.node_type == NodeType.ATTACHMENT
    assert node.attachment_id == file.id
    assert "[f.png]" in (node.payload or "")


def test_insert_text_node_between(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    n1 = add_text_node(db_session, note.id, user, "first")
    n2 = add_text_node(db_session, note.id, user, "third")

    mid = insert_text_node(
        db_session,
        note.id,
        user,
        "second",
        after_node_id=n1.id,
        before_node_id=n2.id,
    )

    assert n1.position < mid.position < n2.position
    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [n.payload for n in nodes] == ["first", "second", "third"]


def test_insert_text_node_at_start(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    n1 = add_text_node(db_session, note.id, user, "second")

    before = insert_text_node(
        db_session,
        note.id,
        user,
        "first",
        before_node_id=n1.id,
    )

    assert before.position < n1.position


def test_mixed_text_and_attachment_nodes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    file = File(note_id=note.id, file_name="img.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()

    n1 = add_text_node(db_session, note.id, user, "text1")
    n2 = add_attachment_node(db_session, note.id, user, file.id)
    n3 = add_text_node(db_session, note.id, user, "text2")

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert len(nodes) == 3
    assert nodes[0].id == n1.id
    assert nodes[1].id == n2.id
    assert nodes[2].id == n3.id


# -----------------------------------------------------------------------
# Optimistic locking — update
# -----------------------------------------------------------------------


def test_update_text_node_success(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "old")

    updated = update_text_node(db_session, node.id, user, "new", 1)
    assert updated.payload == "new"
    assert updated.version == 2


def test_update_text_node_version_conflict(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "v1")

    update_text_node(db_session, node.id, user, "v2", 1)

    with pytest.raises(NodeVersionConflictError) as exc_info:
        update_text_node(db_session, node.id, user, "v3", 1)
    assert exc_info.value.expected_version == 1
    assert exc_info.value.actual_version == 2


def test_update_text_node_not_found(db_session: Session) -> None:
    user = _make_user(db_session)
    with pytest.raises(NodeNotFoundError):
        update_text_node(db_session, uuid.uuid4(), user, "x", 1)


# -----------------------------------------------------------------------
# Split / merge
# -----------------------------------------------------------------------


def test_split_text_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "HelloWorld")

    left, right = split_text_node(db_session, node.id, user, 5, 1)

    assert left.payload == "Hello"
    assert right.payload == "World"
    assert left.position < right.position
    assert left.version == 2
    assert right.version == 1

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [n.payload for n in nodes] == ["Hello", "World"]


def test_split_preserves_surrounding_order(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    n1 = add_text_node(db_session, note.id, user, "first")
    n2 = add_text_node(db_session, note.id, user, "splitme")
    n3 = add_text_node(db_session, note.id, user, "last")

    _left, _right = split_text_node(db_session, n2.id, user, 5, 1)

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [n.payload for n in nodes] == ["first", "split", "me", "last"]
    assert nodes[0].id == n1.id
    assert nodes[3].id == n3.id


def test_split_text_node_version_conflict(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "text")

    update_text_node(db_session, node.id, user, "updated", 1)

    with pytest.raises(NodeVersionConflictError):
        split_text_node(db_session, node.id, user, 2, 1)


def test_merge_text_nodes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    n1 = add_text_node(db_session, note.id, user, "Hello")
    n2 = add_text_node(db_session, note.id, user, " World")

    merged = merge_text_nodes(db_session, n2.id, user, n1.id, 1, 1)
    assert merged.payload == "Hello World"
    assert merged.version == 2

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert len(nodes) == 1
    assert nodes[0].payload == "Hello World"


def test_merge_text_nodes_version_conflict_source(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    n1 = add_text_node(db_session, note.id, user, "A")
    n2 = add_text_node(db_session, note.id, user, "B")
    update_text_node(db_session, n2.id, user, "B2", 1)

    with pytest.raises(NodeVersionConflictError):
        merge_text_nodes(db_session, n2.id, user, n1.id, 1, 1)


def test_merge_text_nodes_version_conflict_target(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    n1 = add_text_node(db_session, note.id, user, "A")
    n2 = add_text_node(db_session, note.id, user, "B")
    update_text_node(db_session, n1.id, user, "A2", 1)

    with pytest.raises(NodeVersionConflictError):
        merge_text_nodes(db_session, n2.id, user, n1.id, 1, 1)


# -----------------------------------------------------------------------
# Node type validation
# -----------------------------------------------------------------------


def test_split_rejects_attachment_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()
    node = add_attachment_node(db_session, note.id, user, file.id)

    with pytest.raises(InvalidNodeTypeError):
        split_text_node(db_session, node.id, user, 0, 1)


def test_merge_rejects_attachment_source(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()
    text_node = add_text_node(db_session, note.id, user, "text")
    att_node = add_attachment_node(db_session, note.id, user, file.id)

    with pytest.raises(InvalidNodeTypeError):
        merge_text_nodes(db_session, att_node.id, user, text_node.id, 1, 1)


def test_merge_rejects_attachment_target(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()
    text_node = add_text_node(db_session, note.id, user, "text")
    att_node = add_attachment_node(db_session, note.id, user, file.id)

    with pytest.raises(InvalidNodeTypeError):
        merge_text_nodes(db_session, text_node.id, user, att_node.id, 1, 1)


# -----------------------------------------------------------------------
# Delete
# -----------------------------------------------------------------------


def test_delete_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "text")

    delete_node(db_session, node.id, user)
    assert db_session.query(Node).count() == 0


def test_delete_node_idempotent(db_session: Session) -> None:
    user = _make_user(db_session)
    random_id = uuid.uuid4()
    delete_node(db_session, random_id, user)


# -----------------------------------------------------------------------
# Ordering stress test
# -----------------------------------------------------------------------


def test_many_inserts_maintain_order(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    for i in range(20):
        add_text_node(db_session, note.id, user, str(i))

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [n.payload for n in nodes] == [str(i) for i in range(20)]


def test_update_touches_note_timestamp(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    original_ts = note.update_timestamp.replace(tzinfo=None)

    node = add_text_node(db_session, note.id, user, "v1")
    update_text_node(db_session, node.id, user, "v2", 1)

    db_session.expire(note)
    updated_ts = note.update_timestamp
    if updated_ts.tzinfo is not None:
        updated_ts = updated_ts.replace(tzinfo=None)
    assert updated_ts >= original_ts


# -----------------------------------------------------------------------
# Markdown node operations
# -----------------------------------------------------------------------


def test_add_markdown_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    node = add_markdown_node(db_session, note.id, user, "# Title", "heading")
    assert node.node_type == NodeType.MARKDOWN
    assert node.block_type == "heading"
    assert node.payload == "# Title"
    assert node.version == 1


def test_add_markdown_node_invalid_block_type(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    with pytest.raises(InvalidBlockTypeError):
        add_markdown_node(db_session, note.id, user, "text", "invalid_type")


def test_insert_markdown_node_between(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    n1 = add_markdown_node(db_session, note.id, user, "# Title", "heading")
    n3 = add_markdown_node(db_session, note.id, user, "paragraph text", "paragraph")

    n2 = insert_markdown_node(
        db_session,
        note.id,
        user,
        "> quote",
        "blockquote",
        after_node_id=n1.id,
        before_node_id=n3.id,
    )

    assert n1.position < n2.position < n3.position
    assert n2.block_type == "blockquote"
    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [n.payload for n in nodes] == ["# Title", "> quote", "paragraph text"]


def test_update_markdown_node_success(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_markdown_node(db_session, note.id, user, "old", "paragraph")

    updated = update_markdown_node(
        db_session,
        node.id,
        user,
        "# new heading",
        "heading",
        1,
    )
    assert updated.payload == "# new heading"
    assert updated.block_type == "heading"
    assert updated.version == 2


def test_update_markdown_node_version_conflict(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_markdown_node(db_session, note.id, user, "v1", "paragraph")

    update_markdown_node(db_session, node.id, user, "v2", "paragraph", 1)

    with pytest.raises(NodeVersionConflictError) as exc_info:
        update_markdown_node(db_session, node.id, user, "v3", "paragraph", 1)
    assert exc_info.value.expected_version == 1
    assert exc_info.value.actual_version == 2


def test_update_markdown_node_rejects_text_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "text")

    with pytest.raises(InvalidNodeTypeError):
        update_markdown_node(db_session, node.id, user, "new", "paragraph", 1)


def test_markdown_and_text_nodes_coexist(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    add_text_node(db_session, note.id, user, "plain text")
    add_markdown_node(db_session, note.id, user, "# Heading", "heading")
    add_markdown_node(db_session, note.id, user, "para", "paragraph")

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert len(nodes) == 3
    assert nodes[0].node_type == NodeType.TEXT
    assert nodes[0].block_type is None
    assert nodes[1].node_type == NodeType.MARKDOWN
    assert nodes[1].block_type == "heading"
    assert nodes[2].block_type == "paragraph"


def test_delete_markdown_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    node = add_markdown_node(db_session, note.id, user, "# Title", "heading")
    delete_node(db_session, node.id, user)

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert len(nodes) == 0


# -----------------------------------------------------------------------
# Replace markdown nodes (bulk import override)
# -----------------------------------------------------------------------


def test_replace_markdown_nodes_on_empty_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    created = replace_markdown_nodes(
        db_session,
        note.id,
        user,
        [("heading", "# Title"), ("paragraph", "Body text")],
    )

    assert [n.payload for n in created] == ["# Title", "Body text"]
    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [n.payload for n in nodes] == ["# Title", "Body text"]
    assert [n.block_type for n in nodes] == ["heading", "paragraph"]
    assert nodes[0].position < nodes[1].position


def test_replace_markdown_nodes_deletes_existing(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    add_markdown_node(db_session, note.id, user, "old content", "paragraph")

    replace_markdown_nodes(db_session, note.id, user, [("paragraph", "new content")])

    nodes = get_ordered_nodes(db_session, note.id, user)
    assert len(nodes) == 1
    assert nodes[0].payload == "new content"


def test_replace_markdown_nodes_touches_note_timestamp(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    original_ts = note.update_timestamp.replace(tzinfo=None)

    replace_markdown_nodes(db_session, note.id, user, [("paragraph", "content")])

    db_session.expire(note)
    updated_ts = note.update_timestamp
    if updated_ts.tzinfo is not None:
        updated_ts = updated_ts.replace(tzinfo=None)
    assert updated_ts >= original_ts


# -----------------------------------------------------------------------
# Authorization — Notebook CRUD
# -----------------------------------------------------------------------


def _grant(
    session: Session,
    principal: User,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
    role_name: RoleName,
) -> Entitlement:
    entitlement = Entitlement(
        principal_id=principal.uid,
        note_id=note_id,
        notebook_id=notebook_id,
        role_name=role_name.value,
    )
    session.add(entitlement)
    session.flush()
    return entitlement


def test_create_notebook_auto_grants_owner_entitlement(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)

    entitlement = db_session.scalar(
        select(Entitlement).where(
            Entitlement.notebook_id == nb.id,
            Entitlement.principal_id == user.uid,
        ),
    )
    assert entitlement is not None
    assert entitlement.role_name == RoleName.NOTEBOOK_OWNER.value


def test_create_note_auto_grants_owner_entitlement(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)
    note = create_note(db_session, nb.id, user, "Note")

    entitlement = db_session.scalar(
        select(Entitlement).where(
            Entitlement.note_id == note.id,
            Entitlement.principal_id == user.uid,
        ),
    )
    assert entitlement is not None
    assert entitlement.role_name == RoleName.NOTE_OWNER.value


def test_get_notebook_denied_for_unrelated_user(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = create_notebook(db_session, "Work", owner)

    with pytest.raises(NotebookNotFoundError):
        get_notebook(db_session, nb.id, other)


def test_get_notebook_succeeds_for_viewer(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    _grant(db_session, viewer, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_VIEWER)

    fetched = get_notebook(db_session, nb.id, viewer)
    assert fetched.id == nb.id


def test_update_notebook_denied_for_viewer(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    _grant(db_session, viewer, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_VIEWER)

    with pytest.raises(PermissionDeniedError):
        update_notebook(db_session, nb.id, viewer, name="New Name")


def test_update_notebook_succeeds_for_editor(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    nb = create_notebook(db_session, "Work", owner)
    _grant(db_session, editor, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_EDITOR)

    updated = update_notebook(db_session, nb.id, editor, name="New Name")
    assert updated.name == "New Name"


def test_delete_notebook_denied_for_editor(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    nb = create_notebook(db_session, "Work", owner)
    _grant(db_session, editor, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_EDITOR)

    with pytest.raises(PermissionDeniedError):
        delete_notebook(db_session, nb.id, editor)


# -----------------------------------------------------------------------
# Authorization — Note CRUD
# -----------------------------------------------------------------------


def test_create_note_denied_without_create_notes(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    _grant(db_session, viewer, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_VIEWER)

    with pytest.raises(PermissionDeniedError):
        create_note(db_session, nb.id, viewer, "Sneaky")


def test_create_note_succeeds_for_editor(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    nb = create_notebook(db_session, "Work", owner)
    _grant(db_session, editor, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_EDITOR)

    note = create_note(db_session, nb.id, editor, "Note")
    assert note.owner_id == editor.uid


def test_update_note_denied_for_note_viewer(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    note = create_note(db_session, nb.id, owner, "Note")
    _grant(db_session, viewer, note_id=note.id, role_name=RoleName.NOTE_VIEWER)

    with pytest.raises(PermissionDeniedError):
        update_note(db_session, note.id, viewer, title="Hacked")


def test_update_note_succeeds_for_note_editor(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    nb = create_notebook(db_session, "Work", owner)
    note = create_note(db_session, nb.id, owner, "Note")
    _grant(db_session, editor, note_id=note.id, role_name=RoleName.NOTE_EDITOR)

    updated = update_note(db_session, note.id, editor, title="Updated")
    assert updated.title == "Updated"


def test_delete_note_denied_for_note_editor(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    nb = create_notebook(db_session, "Work", owner)
    note = create_note(db_session, nb.id, owner, "Note")
    _grant(db_session, editor, note_id=note.id, role_name=RoleName.NOTE_EDITOR)

    with pytest.raises(PermissionDeniedError):
        delete_note(db_session, note.id, editor)


def test_delete_note_succeeds_via_notebook_delete_notes(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    deleter = _make_user(db_session, "deleter@test.com")
    nb = create_notebook(db_session, "Work", owner)
    note = create_note(db_session, nb.id, owner, "Note")
    _grant(
        db_session,
        deleter,
        notebook_id=nb.id,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    # NOTEBOOK_VIEWER alone doesn't grant delete_notes, so add a direct
    # permission-level entitlement carrying only DELETE_NOTES.
    db_session.add(
        Entitlement(
            principal_id=deleter.uid,
            notebook_id=nb.id,
            permission_name=PermissionName.DELETE_NOTES.value,
        ),
    )
    db_session.flush()

    delete_note(db_session, note.id, deleter)
    assert db_session.get(Note, note.id) is None


def test_node_mutation_denied_for_note_viewer(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    note = create_note(db_session, nb.id, owner, "Note")
    _grant(db_session, viewer, note_id=note.id, role_name=RoleName.NOTE_VIEWER)

    with pytest.raises(PermissionDeniedError):
        add_text_node(db_session, note.id, viewer, "hi")


def test_get_ordered_nodes_denied_for_unrelated_user(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = create_notebook(db_session, "Work", owner)
    note = create_note(db_session, nb.id, owner, "Note")

    with pytest.raises(NoteNotFoundError):
        get_ordered_nodes(db_session, note.id, other)


# -----------------------------------------------------------------------
# Authorization — list_notebooks / list_notes scoping
# -----------------------------------------------------------------------


def test_list_notebooks_includes_directly_shared_notebook(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    mine = create_notebook(db_session, "Mine", viewer)
    shared = create_notebook(db_session, "Shared", owner)
    _grant(db_session, viewer, notebook_id=shared.id, role_name=RoleName.NOTEBOOK_VIEWER)
    create_notebook(db_session, "Unrelated", owner)

    visible = {nb.id for nb in list_notebooks(db_session, viewer)}
    assert visible == {mine.id, shared.id}


def test_list_notebooks_includes_notebook_via_single_shared_note(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    note = create_note(db_session, nb.id, owner, "Note")
    _grant(db_session, viewer, note_id=note.id, role_name=RoleName.NOTE_VIEWER)

    visible = {nb2.id for nb2 in list_notebooks(db_session, viewer)}
    assert visible == {nb.id}


def test_list_notes_returns_all_with_view_notes(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    create_note(db_session, nb.id, owner, "Note1")
    create_note(db_session, nb.id, owner, "Note2")
    _grant(db_session, viewer, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_VIEWER)

    assert len(list_notes(db_session, nb.id, viewer)) == 2


def test_list_notes_returns_only_directly_shared_notes(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = create_notebook(db_session, "Work", owner)
    shared_note = create_note(db_session, nb.id, owner, "Shared")
    create_note(db_session, nb.id, owner, "Not shared")
    _grant(db_session, viewer, note_id=shared_note.id, role_name=RoleName.NOTE_VIEWER)

    notes = list_notes(db_session, nb.id, viewer)
    assert [n.id for n in notes] == [shared_note.id]


def test_list_notes_denied_without_notebook_view(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = create_notebook(db_session, "Work", owner)

    with pytest.raises(NotebookNotFoundError):
        list_notes(db_session, nb.id, other)


# -----------------------------------------------------------------------
# Authorization — atomicity of owner-entitlement creation
# -----------------------------------------------------------------------


def test_create_notebook_entitlement_failure_leaves_no_orphaned_notebook(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _make_user(db_session)

    def _boom(*_args: object, **_kwargs: object) -> None:
        msg = "simulated entitlement failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(service_module, "_grant_owner_entitlement", _boom)

    with pytest.raises(RuntimeError):
        create_notebook(db_session, "Work", user)

    db_session.rollback()
    assert db_session.scalar(select(Notebook).where(Notebook.name == "Work")) is None


def test_create_note_entitlement_failure_leaves_no_orphaned_note(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user)

    def _boom(*_args: object, **_kwargs: object) -> None:
        msg = "simulated entitlement failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(service_module, "_grant_owner_entitlement", _boom)

    with pytest.raises(RuntimeError):
        create_note(db_session, nb.id, user, "Orphan")

    db_session.rollback()
    assert db_session.scalar(select(Note).where(Note.title == "Orphan")) is None


# -----------------------------------------------------------------------
# URL-scoping helpers (no permission check — see docstrings)
# -----------------------------------------------------------------------


def test_validate_note_in_notebook_succeeds_for_matching_pair(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")

    validate_note_in_notebook(db_session, nb.id, note.id)


def test_validate_note_in_notebook_raises_for_wrong_notebook(db_session: Session) -> None:
    user = _make_user(db_session)
    nb1 = create_notebook(db_session, "NB1", user)
    nb2 = create_notebook(db_session, "NB2", user)
    note = create_note(db_session, nb1.id, user, "N")

    with pytest.raises(NoteNotFoundError):
        validate_note_in_notebook(db_session, nb2.id, note.id)


def test_validate_note_in_notebook_raises_for_missing_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)

    with pytest.raises(NoteNotFoundError):
        validate_note_in_notebook(db_session, nb.id, uuid.uuid4())


def test_validate_note_in_notebook_does_not_check_permission(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    nb = create_notebook(db_session, "NB", owner)
    note = create_note(db_session, nb.id, owner, "N")

    # No caller_id/permission argument at all: this succeeds purely because
    # the note belongs to the notebook, regardless of who's asking.
    validate_note_in_notebook(db_session, nb.id, note.id)


def test_get_node_in_note_returns_node_for_matching_triple(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "hi")

    found = get_node_in_note(db_session, nb.id, note.id, node.id)
    assert found.id == node.id


def test_get_node_in_note_raises_for_node_in_different_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note1 = create_note(db_session, nb.id, user, "N1")
    note2 = create_note(db_session, nb.id, user, "N2")
    node = add_text_node(db_session, note1.id, user, "hi")

    with pytest.raises(NodeNotFoundError):
        get_node_in_note(db_session, nb.id, note2.id, node.id)


def test_validate_node_in_note_succeeds_for_matching_pair(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "hi")

    validate_node_in_note(db_session, note.id, node.id)


def test_validate_node_in_note_raises_for_wrong_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note1 = create_note(db_session, nb.id, user, "N1")
    note2 = create_note(db_session, nb.id, user, "N2")
    node = add_text_node(db_session, note1.id, user, "hi")

    with pytest.raises(NodeNotFoundError):
        validate_node_in_note(db_session, note2.id, node.id)


def test_delete_node_returns_attachment_id_for_attachment_node(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()
    node = add_attachment_node(db_session, note.id, user, file.id)

    result = delete_node(db_session, node.id, user)
    assert result == file.id


def test_delete_node_returns_none_for_text_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "N")
    node = add_text_node(db_session, note.id, user, "hi")

    assert delete_node(db_session, node.id, user) is None


def test_delete_node_returns_none_for_absent_node(db_session: Session) -> None:
    user = _make_user(db_session)
    assert delete_node(db_session, uuid.uuid4(), user) is None
