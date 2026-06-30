"""Tests for Notes Service ORM models."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from assistant.models.schema import (
    File,
    FileState,
    Node,
    NodeType,
    Note,
    Notebook,
    User,
)


def _create_user(session: Session, email: str = "test@example.com") -> User:
    user = User(
        email=email,
        firstname="Test",
        lastname="User",
    )
    session.add(user)
    session.flush()
    return user


def _create_notebook(
    session: Session,
    user: User,
    name: str = "Test Notebook",
) -> Notebook:
    notebook = Notebook(name=name, owner_id=user.uid)
    session.add(notebook)
    session.flush()
    return notebook


def _create_note(
    session: Session,
    notebook: Notebook,
    user: User,
    title: str = "Test Note",
) -> Note:
    now = datetime.now(UTC)
    note = Note(
        notebook_id=notebook.id,
        owner_id=user.uid,
        title=title,
        creation_timestamp=now,
        update_timestamp=now,
    )
    session.add(note)
    session.flush()
    return note


def test_create_user(db_session: Session) -> None:
    user = _create_user(db_session)
    assert user.uid is not None
    assert user.email == "test@example.com"

    fetched = db_session.get(User, user.uid)
    assert fetched is not None
    assert fetched.firstname == "Test"


def test_create_notebook_with_owner(db_session: Session) -> None:
    user = _create_user(db_session)
    notebook = _create_notebook(db_session, user)

    assert notebook.id is not None
    assert notebook.owner_id == user.uid
    assert notebook.owner.email == "test@example.com"
    assert len(user.notebooks) == 1


def test_create_note_with_relationships(db_session: Session) -> None:
    user = _create_user(db_session)
    notebook = _create_notebook(db_session, user)
    note = _create_note(db_session, notebook, user)

    assert note.id is not None
    assert note.notebook_id == notebook.id
    assert note.owner_id == user.uid
    assert note.notebook.name == "Test Notebook"
    assert note.creation_timestamp is not None
    assert len(notebook.notes) == 1


def test_create_text_node(db_session: Session) -> None:
    user = _create_user(db_session)
    notebook = _create_notebook(db_session, user)
    note = _create_note(db_session, notebook, user)

    node = Node(
        note_id=note.id,
        position="a0",
        author_id=user.uid,
        node_type=NodeType.TEXT,
        payload="Hello, world!",
    )
    db_session.add(node)
    db_session.flush()

    assert node.id is not None
    assert node.version == 1
    assert node.payload == "Hello, world!"
    assert node.node_type == NodeType.TEXT
    assert node.attachment_id is None
    assert node.note.title == "Test Note"
    assert node.author.email == "test@example.com"


def test_create_attachment_node(db_session: Session) -> None:
    user = _create_user(db_session)
    notebook = _create_notebook(db_session, user)
    note = _create_note(db_session, notebook, user)

    file = File(note_id=note.id, file_name="image.png", state=FileState.COMPLETE.value)
    db_session.add(file)
    db_session.flush()

    node = Node(
        note_id=note.id,
        position="a0",
        author_id=user.uid,
        node_type=NodeType.ATTACHMENT,
        attachment_id=file.id,
        payload=f"[image.png](/files/{file.id})",
    )
    db_session.add(node)
    db_session.flush()

    assert node.node_type == NodeType.ATTACHMENT
    assert node.payload is not None
    assert node.attachment is not None
    assert node.attachment.file_name == "image.png"


def test_note_nodes_ordered_by_position(db_session: Session) -> None:
    user = _create_user(db_session)
    notebook = _create_notebook(db_session, user)
    note = _create_note(db_session, notebook, user)

    positions = ["a2", "a0", "a1V", "a1"]
    for pos in positions:
        db_session.add(
            Node(
                note_id=note.id,
                position=pos,
                author_id=user.uid,
                node_type=NodeType.TEXT,
                payload=f"content at {pos}",
            ),
        )
    db_session.flush()

    db_session.expire_all()
    ordered = note.nodes
    assert [n.position for n in ordered] == ["a0", "a1", "a1V", "a2"]


def test_note_cascade_deletes_nodes(db_session: Session) -> None:
    user = _create_user(db_session)
    notebook = _create_notebook(db_session, user)
    note = _create_note(db_session, notebook, user)

    db_session.add(
        Node(
            note_id=note.id,
            position="a0",
            author_id=user.uid,
            node_type=NodeType.TEXT,
            payload="will be deleted",
        ),
    )
    db_session.flush()
    assert db_session.query(Node).count() == 1

    db_session.delete(note)
    db_session.flush()
    assert db_session.query(Node).count() == 0


def test_notebook_cascade_deletes_notes(db_session: Session) -> None:
    user = _create_user(db_session)
    notebook = _create_notebook(db_session, user)
    _create_note(db_session, notebook, user, "Note 1")
    _create_note(db_session, notebook, user, "Note 2")
    db_session.flush()
    assert db_session.query(Note).count() == 2

    db_session.delete(notebook)
    db_session.flush()
    assert db_session.query(Note).count() == 0
