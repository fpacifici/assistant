"""Tests for the per-user tag service and tag propagation on share."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from assistant.models.schema import Note, NoteTag, RoleName, Tag, User
from assistant.notes import tags as tags_module
from assistant.notes.entitlements import grant_entitlement
from assistant.notes.exceptions import (
    InvalidTagNameError,
    NoteNotFoundError,
    TagNotFoundError,
)
from assistant.notes.service import create_note, create_notebook, delete_note
from assistant.notes.tags import (
    MAX_TAG_NAME_LENGTH,
    add_tag_to_note,
    copy_note_tags,
    find_or_create_tag,
    get_tag,
    list_tags,
    normalize_tag_name,
    remove_tag_from_note,
    tags_for_notes,
)


def _make_user(session: Session, email: str) -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _make_note(session: Session, owner: User, notebook_name: str = "NB") -> Note:
    notebook = create_notebook(session, notebook_name, owner)
    return create_note(session, notebook_id=notebook.id, owner=owner, title="N")


def _tag_names(session: Session, user: User, note: Note) -> list[str]:
    return [t.name for t in tags_for_notes(session, user, [note.id]).get(note.id, [])]


# --- Normalization ---


def test_normalize_trims_and_casefolds() -> None:
    assert normalize_tag_name("  Work Stuff ") == ("Work Stuff", "work stuff")


@pytest.mark.parametrize("name", ["", "   ", "x" * (MAX_TAG_NAME_LENGTH + 1)])
def test_normalize_rejects_invalid_names(name: str) -> None:
    with pytest.raises(InvalidTagNameError):
        normalize_tag_name(name)


def test_normalize_accepts_max_length() -> None:
    name = "x" * MAX_TAG_NAME_LENGTH
    assert normalize_tag_name(name)[0] == name


# --- Tag vocabulary ---


def test_find_or_create_is_case_insensitive(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")

    tag, created = find_or_create_tag(db_session, user, "Work")
    same, created_again = find_or_create_tag(db_session, user, " work ")

    assert created is True
    assert created_again is False
    assert same.id == tag.id
    assert same.name == "Work"


def test_find_or_create_recovers_from_concurrent_insert(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _make_user(db_session, "u@test.com")
    # Another transaction already inserted the tag, but our first lookup
    # ran before it was visible.
    existing = Tag(owner_id=user.uid, name="Work", normalized_name="work")
    db_session.add(existing)
    db_session.flush()
    real_find = tags_module._find_tag_by_key
    stale_reads = [True]

    def find_stale_once(s: Session, o: uuid.UUID, k: str) -> Tag | None:
        if stale_reads:
            stale_reads.pop()
            return None
        return real_find(s, o, k)

    monkeypatch.setattr(tags_module, "_find_tag_by_key", find_stale_once)

    tag, created = find_or_create_tag(db_session, user, "work")

    assert created is False
    assert tag.id == existing.id
    assert len(list_tags(db_session, user)) == 1


def test_tags_are_scoped_per_user(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")

    alice_tag, _ = find_or_create_tag(db_session, alice, "work")
    bob_tag, _ = find_or_create_tag(db_session, bob, "work")

    assert alice_tag.id != bob_tag.id
    assert [t.id for t in list_tags(db_session, alice)] == [alice_tag.id]
    with pytest.raises(TagNotFoundError):
        get_tag(db_session, bob, alice_tag.id)


def test_list_tags_is_ordered_by_name(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    for name in ["beta", "Alpha", "gamma"]:
        find_or_create_tag(db_session, user, name)

    assert [t.name for t in list_tags(db_session, user)] == ["Alpha", "beta", "gamma"]


def test_get_tag_unknown_id_raises(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    with pytest.raises(TagNotFoundError):
        get_tag(db_session, user, uuid.uuid4())


# --- Tagging notes ---


def test_add_tag_by_name_creates_it_on_the_fly(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    note = _make_note(db_session, user)

    tag = add_tag_to_note(db_session, user, note.id, name="ideas")

    assert tag.owner_id == user.uid
    assert _tag_names(db_session, user, note) == ["ideas"]


def test_add_tag_by_id_is_idempotent(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    note = _make_note(db_session, user)
    tag, _ = find_or_create_tag(db_session, user, "ideas")

    add_tag_to_note(db_session, user, note.id, tag_id=tag.id)
    add_tag_to_note(db_session, user, note.id, tag_id=tag.id)
    add_tag_to_note(db_session, user, note.id, name="IDEAS")

    assert _tag_names(db_session, user, note) == ["ideas"]


def test_add_tag_requires_exactly_one_of_id_or_name(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    note = _make_note(db_session, user)
    tag, _ = find_or_create_tag(db_session, user, "ideas")

    with pytest.raises(ValueError, match="Exactly one"):
        add_tag_to_note(db_session, user, note.id)
    with pytest.raises(ValueError, match="Exactly one"):
        add_tag_to_note(db_session, user, note.id, tag_id=tag.id, name="ideas")


def test_cannot_use_another_users_tag(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    note = _make_note(db_session, alice)
    bob_tag, _ = find_or_create_tag(db_session, bob, "secret")

    with pytest.raises(TagNotFoundError):
        add_tag_to_note(db_session, alice, note.id, tag_id=bob_tag.id)


def test_cannot_tag_a_note_without_access(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    note = _make_note(db_session, alice)

    with pytest.raises(NoteNotFoundError):
        add_tag_to_note(db_session, bob, note.id, name="mine")


def test_viewer_can_tag_a_shared_note(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    note = _make_note(db_session, alice)
    grant_entitlement(
        db_session,
        alice,
        note_id=note.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTE_VIEWER,
    )

    add_tag_to_note(db_session, bob, note.id, name="read-later")

    assert _tag_names(db_session, bob, note) == ["read-later"]
    assert _tag_names(db_session, alice, note) == []


def test_remove_tag_is_idempotent_and_keeps_the_tag(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    note = _make_note(db_session, user)
    tag = add_tag_to_note(db_session, user, note.id, name="ideas")

    remove_tag_from_note(db_session, user, note.id, tag.id)
    remove_tag_from_note(db_session, user, note.id, tag.id)

    assert _tag_names(db_session, user, note) == []
    assert [t.id for t in list_tags(db_session, user)] == [tag.id]


def test_tags_for_notes_batches_and_filters_by_owner(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    nb = create_notebook(db_session, "NB", alice)
    n1 = create_note(db_session, notebook_id=nb.id, owner=alice, title="1")
    n2 = create_note(db_session, notebook_id=nb.id, owner=alice, title="2")
    n3 = create_note(db_session, notebook_id=nb.id, owner=alice, title="3")
    add_tag_to_note(db_session, alice, n1.id, name="b")
    add_tag_to_note(db_session, alice, n1.id, name="a")
    add_tag_to_note(db_session, alice, n2.id, name="a")

    result = tags_for_notes(db_session, alice, [n1.id, n2.id, n3.id])

    assert {k: [t.name for t in v] for k, v in result.items()} == {
        n1.id: ["a", "b"],
        n2.id: ["a"],
    }
    assert tags_for_notes(db_session, bob, [n1.id, n2.id]) == {}
    assert tags_for_notes(db_session, alice, []) == {}


def test_deleting_a_note_removes_its_tag_links(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    note = _make_note(db_session, user)
    add_tag_to_note(db_session, user, note.id, name="ideas")

    delete_note(db_session, note.id, user)

    assert db_session.scalars(select(NoteTag)).all() == []
    assert [t.name for t in list_tags(db_session, user)] == ["ideas"]


# --- Propagation on share ---


def test_note_share_creates_missing_tags_for_recipient(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    note = _make_note(db_session, alice)
    add_tag_to_note(db_session, alice, note.id, name="Work")
    add_tag_to_note(db_session, alice, note.id, name="urgent")

    grant_entitlement(
        db_session,
        alice,
        note_id=note.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTE_VIEWER,
    )

    assert _tag_names(db_session, bob, note) == ["urgent", "Work"]
    bob_tags = list_tags(db_session, bob)
    assert all(t.owner_id == bob.uid for t in bob_tags)
    assert _tag_names(db_session, alice, note) == ["urgent", "Work"]


def test_note_share_reuses_recipients_existing_tag(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    note = _make_note(db_session, alice)
    add_tag_to_note(db_session, alice, note.id, name="Work")
    bob_work, _ = find_or_create_tag(db_session, bob, "WORK")

    grant_entitlement(
        db_session,
        alice,
        note_id=note.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTE_EDITOR,
    )

    bob_note_tags = tags_for_notes(db_session, bob, [note.id])[note.id]
    assert [t.id for t in bob_note_tags] == [bob_work.id]
    assert len(list_tags(db_session, bob)) == 1


def test_notebook_share_propagates_tags_of_all_notes(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    nb = create_notebook(db_session, "NB", alice)
    n1 = create_note(db_session, notebook_id=nb.id, owner=alice, title="1")
    n2 = create_note(db_session, notebook_id=nb.id, owner=alice, title="2")
    add_tag_to_note(db_session, alice, n1.id, name="shared")
    add_tag_to_note(db_session, alice, n2.id, name="shared")
    add_tag_to_note(db_session, alice, n2.id, name="other")

    grant_entitlement(
        db_session,
        alice,
        notebook_id=nb.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )

    assert _tag_names(db_session, bob, n1) == ["shared"]
    assert _tag_names(db_session, bob, n2) == ["other", "shared"]
    assert [t.name for t in list_tags(db_session, bob)] == ["other", "shared"]


def test_reshare_does_not_restore_removed_tags(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    note = _make_note(db_session, alice)
    add_tag_to_note(db_session, alice, note.id, name="Work")
    share_kwargs = {
        "note_id": note.id,
        "grantee_email": bob.email,
        "role_name": RoleName.NOTE_VIEWER,
    }
    grant_entitlement(db_session, alice, **share_kwargs)  # type: ignore[arg-type]
    bob_tag = tags_for_notes(db_session, bob, [note.id])[note.id][0]
    remove_tag_from_note(db_session, bob, note.id, bob_tag.id)

    _, created = grant_entitlement(db_session, alice, **share_kwargs)  # type: ignore[arg-type]

    assert created is False
    assert _tag_names(db_session, bob, note) == []


def test_share_uses_the_granters_tags_not_the_owners(db_session: Session) -> None:
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    carol = _make_user(db_session, "carol@test.com")
    note = _make_note(db_session, alice)
    grant_entitlement(
        db_session,
        alice,
        note_id=note.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTE_OWNER,
    )
    # Tagged after Bob's share, so only Alice sees this one.
    add_tag_to_note(db_session, alice, note.id, name="alice-only")
    add_tag_to_note(db_session, bob, note.id, name="bob-only")

    grant_entitlement(
        db_session,
        bob,
        note_id=note.id,
        grantee_email=carol.email,
        role_name=RoleName.NOTE_VIEWER,
    )

    assert _tag_names(db_session, carol, note) == ["bob-only"]


def test_copy_to_self_is_a_noop(db_session: Session) -> None:
    user = _make_user(db_session, "u@test.com")
    note = _make_note(db_session, user)
    add_tag_to_note(db_session, user, note.id, name="ideas")

    copy_note_tags(db_session, source=user, target=user, note_ids=[note.id])

    assert db_session.scalars(select(Tag)).all() == list_tags(db_session, user)
    assert _tag_names(db_session, user, note) == ["ideas"]
