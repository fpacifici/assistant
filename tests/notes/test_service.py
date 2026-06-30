"""Tests for the Notes service module."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from assistant.models.schema import (
    File,
    FileState,
    Node,
    NodeType,
    Note,
    User,
)
from assistant.notes.exceptions import (
    InvalidBlockTypeError,
    InvalidNodeTypeError,
    NodeNotFoundError,
    NodeVersionConflictError,
    NotebookNotFoundError,
    NoteNotFoundError,
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
    get_note,
    get_notebook,
    get_ordered_nodes,
    insert_markdown_node,
    insert_text_node,
    list_notebooks,
    list_notes,
    merge_text_nodes,
    split_text_node,
    update_markdown_node,
    update_text_node,
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
    nb = create_notebook(db_session, "Work", user.uid)
    assert nb.id is not None
    assert nb.name == "Work"
    assert nb.owner_id == user.uid


def test_get_notebook(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user.uid)
    fetched = get_notebook(db_session, nb.id)
    assert fetched.id == nb.id


def test_get_notebook_not_found(db_session: Session) -> None:
    with pytest.raises(NotebookNotFoundError):
        get_notebook(db_session, uuid.uuid4())


def test_list_notebooks_filters_by_owner(db_session: Session) -> None:
    u1 = _make_user(db_session, "a@test.com")
    u2 = _make_user(db_session, "b@test.com")
    create_notebook(db_session, "NB1", u1.uid)
    create_notebook(db_session, "NB2", u1.uid)
    create_notebook(db_session, "NB3", u2.uid)

    assert len(list_notebooks(db_session, u1.uid)) == 2
    assert len(list_notebooks(db_session, u2.uid)) == 1


def test_delete_notebook_cascades(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user.uid)
    note = create_note(db_session, nb.id, user.uid, "Note")
    add_text_node(db_session, note.id, user.uid, "content")

    delete_notebook(db_session, nb.id)

    assert db_session.query(Note).count() == 0
    assert db_session.query(Node).count() == 0


def test_delete_notebook_not_found(db_session: Session) -> None:
    with pytest.raises(NotebookNotFoundError):
        delete_notebook(db_session, uuid.uuid4())


# -----------------------------------------------------------------------
# Note CRUD
# -----------------------------------------------------------------------


def test_create_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user.uid)
    note = create_note(db_session, nb.id, user.uid, "My Note")

    assert note.id is not None
    assert note.title == "My Note"
    assert note.creation_timestamp is not None
    assert note.update_timestamp is not None


def test_get_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user.uid)
    note = create_note(db_session, nb.id, user.uid, "Note")
    fetched = get_note(db_session, note.id)
    assert fetched.id == note.id


def test_get_note_not_found(db_session: Session) -> None:
    with pytest.raises(NoteNotFoundError):
        get_note(db_session, uuid.uuid4())


def test_list_notes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user.uid)
    create_note(db_session, nb.id, user.uid, "Note 1")
    create_note(db_session, nb.id, user.uid, "Note 2")

    assert len(list_notes(db_session, nb.id)) == 2


def test_delete_note_cascades_nodes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "Work", user.uid)
    note = create_note(db_session, nb.id, user.uid, "Note")
    add_text_node(db_session, note.id, user.uid, "p1")
    add_text_node(db_session, note.id, user.uid, "p2")

    delete_note(db_session, note.id)
    assert db_session.query(Node).count() == 0


# -----------------------------------------------------------------------
# Node operations — add / insert
# -----------------------------------------------------------------------


def test_add_text_node_to_empty_note(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    node = add_text_node(db_session, note.id, user.uid, "Hello")
    assert node.payload == "Hello"
    assert node.node_type == NodeType.TEXT
    assert node.version == 1
    assert node.position is not None


def test_add_text_nodes_append_in_order(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    n1 = add_text_node(db_session, note.id, user.uid, "first")
    n2 = add_text_node(db_session, note.id, user.uid, "second")
    n3 = add_text_node(db_session, note.id, user.uid, "third")

    assert n1.position < n2.position < n3.position
    nodes = get_ordered_nodes(db_session, note.id)
    assert [n.payload for n in nodes] == ["first", "second", "third"]


def test_add_attachment_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()

    node = add_attachment_node(db_session, note.id, user.uid, file.id)
    assert node.node_type == NodeType.ATTACHMENT
    assert node.attachment_id == file.id
    assert "[f.png]" in (node.payload or "")


def test_insert_text_node_between(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    n1 = add_text_node(db_session, note.id, user.uid, "first")
    n2 = add_text_node(db_session, note.id, user.uid, "third")

    mid = insert_text_node(
        db_session,
        note.id,
        user.uid,
        "second",
        after_node_id=n1.id,
        before_node_id=n2.id,
    )

    assert n1.position < mid.position < n2.position
    nodes = get_ordered_nodes(db_session, note.id)
    assert [n.payload for n in nodes] == ["first", "second", "third"]


def test_insert_text_node_at_start(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    n1 = add_text_node(db_session, note.id, user.uid, "second")

    before = insert_text_node(
        db_session,
        note.id,
        user.uid,
        "first",
        before_node_id=n1.id,
    )

    assert before.position < n1.position


def test_mixed_text_and_attachment_nodes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    file = File(note_id=note.id, file_name="img.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()

    n1 = add_text_node(db_session, note.id, user.uid, "text1")
    n2 = add_attachment_node(db_session, note.id, user.uid, file.id)
    n3 = add_text_node(db_session, note.id, user.uid, "text2")

    nodes = get_ordered_nodes(db_session, note.id)
    assert len(nodes) == 3
    assert nodes[0].id == n1.id
    assert nodes[1].id == n2.id
    assert nodes[2].id == n3.id


# -----------------------------------------------------------------------
# Optimistic locking — update
# -----------------------------------------------------------------------


def test_update_text_node_success(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_text_node(db_session, note.id, user.uid, "old")

    updated = update_text_node(db_session, node.id, "new", 1)
    assert updated.payload == "new"
    assert updated.version == 2


def test_update_text_node_version_conflict(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_text_node(db_session, note.id, user.uid, "v1")

    update_text_node(db_session, node.id, "v2", 1)

    with pytest.raises(NodeVersionConflictError) as exc_info:
        update_text_node(db_session, node.id, "v3", 1)
    assert exc_info.value.expected_version == 1
    assert exc_info.value.actual_version == 2


def test_update_text_node_not_found(db_session: Session) -> None:
    with pytest.raises(NodeNotFoundError):
        update_text_node(db_session, uuid.uuid4(), "x", 1)


# -----------------------------------------------------------------------
# Split / merge
# -----------------------------------------------------------------------


def test_split_text_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_text_node(db_session, note.id, user.uid, "HelloWorld")

    left, right = split_text_node(db_session, node.id, user.uid, 5, 1)

    assert left.payload == "Hello"
    assert right.payload == "World"
    assert left.position < right.position
    assert left.version == 2
    assert right.version == 1

    nodes = get_ordered_nodes(db_session, note.id)
    assert [n.payload for n in nodes] == ["Hello", "World"]


def test_split_preserves_surrounding_order(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    n1 = add_text_node(db_session, note.id, user.uid, "first")
    n2 = add_text_node(db_session, note.id, user.uid, "splitme")
    n3 = add_text_node(db_session, note.id, user.uid, "last")

    _left, _right = split_text_node(db_session, n2.id, user.uid, 5, 1)

    nodes = get_ordered_nodes(db_session, note.id)
    assert [n.payload for n in nodes] == ["first", "split", "me", "last"]
    assert nodes[0].id == n1.id
    assert nodes[3].id == n3.id


def test_split_text_node_version_conflict(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_text_node(db_session, note.id, user.uid, "text")

    update_text_node(db_session, node.id, "updated", 1)

    with pytest.raises(NodeVersionConflictError):
        split_text_node(db_session, node.id, user.uid, 2, 1)


def test_merge_text_nodes(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    n1 = add_text_node(db_session, note.id, user.uid, "Hello")
    n2 = add_text_node(db_session, note.id, user.uid, " World")

    merged = merge_text_nodes(db_session, n2.id, n1.id, 1, 1)
    assert merged.payload == "Hello World"
    assert merged.version == 2

    nodes = get_ordered_nodes(db_session, note.id)
    assert len(nodes) == 1
    assert nodes[0].payload == "Hello World"


def test_merge_text_nodes_version_conflict_source(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    n1 = add_text_node(db_session, note.id, user.uid, "A")
    n2 = add_text_node(db_session, note.id, user.uid, "B")
    update_text_node(db_session, n2.id, "B2", 1)

    with pytest.raises(NodeVersionConflictError):
        merge_text_nodes(db_session, n2.id, n1.id, 1, 1)


def test_merge_text_nodes_version_conflict_target(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    n1 = add_text_node(db_session, note.id, user.uid, "A")
    n2 = add_text_node(db_session, note.id, user.uid, "B")
    update_text_node(db_session, n1.id, "A2", 1)

    with pytest.raises(NodeVersionConflictError):
        merge_text_nodes(db_session, n2.id, n1.id, 1, 1)


# -----------------------------------------------------------------------
# Node type validation
# -----------------------------------------------------------------------


def test_split_rejects_attachment_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()
    node = add_attachment_node(db_session, note.id, user.uid, file.id)

    with pytest.raises(InvalidNodeTypeError):
        split_text_node(db_session, node.id, user.uid, 0, 1)


def test_merge_rejects_attachment_source(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()
    text_node = add_text_node(db_session, note.id, user.uid, "text")
    att_node = add_attachment_node(db_session, note.id, user.uid, file.id)

    with pytest.raises(InvalidNodeTypeError):
        merge_text_nodes(db_session, att_node.id, text_node.id, 1, 1)


def test_merge_rejects_attachment_target(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    file = File(note_id=note.id, file_name="f.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()
    text_node = add_text_node(db_session, note.id, user.uid, "text")
    att_node = add_attachment_node(db_session, note.id, user.uid, file.id)

    with pytest.raises(InvalidNodeTypeError):
        merge_text_nodes(db_session, text_node.id, att_node.id, 1, 1)


# -----------------------------------------------------------------------
# Delete
# -----------------------------------------------------------------------


def test_delete_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_text_node(db_session, note.id, user.uid, "text")

    delete_node(db_session, node.id)
    assert db_session.query(Node).count() == 0


def test_delete_node_idempotent(db_session: Session) -> None:
    random_id = uuid.uuid4()
    delete_node(db_session, random_id)


# -----------------------------------------------------------------------
# Ordering stress test
# -----------------------------------------------------------------------


def test_many_inserts_maintain_order(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    for i in range(20):
        add_text_node(db_session, note.id, user.uid, str(i))

    nodes = get_ordered_nodes(db_session, note.id)
    assert [n.payload for n in nodes] == [str(i) for i in range(20)]


def test_update_touches_note_timestamp(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    original_ts = note.update_timestamp.replace(tzinfo=None)

    node = add_text_node(db_session, note.id, user.uid, "v1")
    update_text_node(db_session, node.id, "v2", 1)

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
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    node = add_markdown_node(db_session, note.id, user.uid, "# Title", "heading")
    assert node.node_type == NodeType.MARKDOWN
    assert node.block_type == "heading"
    assert node.payload == "# Title"
    assert node.version == 1


def test_add_markdown_node_invalid_block_type(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    with pytest.raises(InvalidBlockTypeError):
        add_markdown_node(db_session, note.id, user.uid, "text", "invalid_type")


def test_insert_markdown_node_between(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    n1 = add_markdown_node(db_session, note.id, user.uid, "# Title", "heading")
    n3 = add_markdown_node(db_session, note.id, user.uid, "paragraph text", "paragraph")

    n2 = insert_markdown_node(
        db_session,
        note.id,
        user.uid,
        "> quote",
        "blockquote",
        after_node_id=n1.id,
        before_node_id=n3.id,
    )

    assert n1.position < n2.position < n3.position
    assert n2.block_type == "blockquote"
    nodes = get_ordered_nodes(db_session, note.id)
    assert [n.payload for n in nodes] == ["# Title", "> quote", "paragraph text"]


def test_update_markdown_node_success(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_markdown_node(db_session, note.id, user.uid, "old", "paragraph")

    updated = update_markdown_node(db_session, node.id, "# new heading", "heading", 1)
    assert updated.payload == "# new heading"
    assert updated.block_type == "heading"
    assert updated.version == 2


def test_update_markdown_node_version_conflict(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_markdown_node(db_session, note.id, user.uid, "v1", "paragraph")

    update_markdown_node(db_session, node.id, "v2", "paragraph", 1)

    with pytest.raises(NodeVersionConflictError) as exc_info:
        update_markdown_node(db_session, node.id, "v3", "paragraph", 1)
    assert exc_info.value.expected_version == 1
    assert exc_info.value.actual_version == 2


def test_update_markdown_node_rejects_text_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")
    node = add_text_node(db_session, note.id, user.uid, "text")

    with pytest.raises(InvalidNodeTypeError):
        update_markdown_node(db_session, node.id, "new", "paragraph", 1)


def test_markdown_and_text_nodes_coexist(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    add_text_node(db_session, note.id, user.uid, "plain text")
    add_markdown_node(db_session, note.id, user.uid, "# Heading", "heading")
    add_markdown_node(db_session, note.id, user.uid, "para", "paragraph")

    nodes = get_ordered_nodes(db_session, note.id)
    assert len(nodes) == 3
    assert nodes[0].node_type == NodeType.TEXT
    assert nodes[0].block_type is None
    assert nodes[1].node_type == NodeType.MARKDOWN
    assert nodes[1].block_type == "heading"
    assert nodes[2].block_type == "paragraph"


def test_delete_markdown_node(db_session: Session) -> None:
    user = _make_user(db_session)
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "N")

    node = add_markdown_node(db_session, note.id, user.uid, "# Title", "heading")
    delete_node(db_session, node.id)

    nodes = get_ordered_nodes(db_session, note.id)
    assert len(nodes) == 0
