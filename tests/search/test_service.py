"""Tests for the search service, against a real Postgres (`pg_session`).

Notes are created and edited only through the notes service, so these
tests also cover indexing end to end: whatever a user writes must be
findable right away.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from assistant.models.schema import (
    Entitlement,
    File,
    FileState,
    Note,
    PermissionName,
    RoleName,
    User,
)
from assistant.notes.entitlements import grant_entitlement
from assistant.notes.service import (
    add_attachment_node,
    add_markdown_node,
    add_text_node,
    create_note,
    create_notebook,
    delete_node,
    merge_text_nodes,
    replace_markdown_nodes,
    split_text_node,
    update_markdown_node,
    update_note,
)
from assistant.notes.tags import add_tag_to_note, find_or_create_tag
from assistant.search.query import EmptySearchQueryError
from assistant.search.service import DEFAULT_LIMIT, SearchHit, SearchSort, search
from assistant.search.snippets import SnippetSegment

pytestmark = pytest.mark.postgres


def _make_user(session: Session, email: str = "owner@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _make_note(
    session: Session,
    owner: User,
    title: str = "Untitled",
    blocks: tuple[str, ...] = (),
) -> Note:
    notebook = create_notebook(session, f"NB {uuid.uuid4()}", owner)
    note = create_note(session, notebook_id=notebook.id, owner=owner, title=title)
    for payload in blocks:
        add_markdown_node(session, note.id, owner, payload, "paragraph")
    return note


def _hit_ids(session: Session, user: User, query: str) -> list:
    return [hit.note.id for hit in search(session, user, query).hits]


# --- Keyword matching ---


def test_finds_note_by_word_in_a_block(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, blocks=("We fly to Berlin on Monday",))
    _make_note(pg_session, owner, blocks=("Grocery list",))

    assert _hit_ids(pg_session, owner, "berlin") == [match.id]


def test_all_words_must_match_but_may_be_in_different_blocks_or_title(
    pg_session: Session,
) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, title="Trip", blocks=("Budget", "Berlin"))
    _make_note(pg_session, owner, blocks=("Budget only",))

    assert _hit_ids(pg_session, owner, "trip budget berlin ") == [match.id]


def test_matching_ignores_case_and_accents(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, blocks=("Perché no?",))

    assert _hit_ids(pg_session, owner, "PERCHE ") == [match.id]


def test_last_word_matches_as_prefix_while_typing(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, blocks=("Berliner Mauer",))

    assert _hit_ids(pg_session, owner, "berl") == [match.id]
    assert _hit_ids(pg_session, owner, "berl ") == []


def test_phrase_needs_adjacent_words_in_order(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, blocks=("The project plan is ready",))
    _make_note(pg_session, owner, blocks=("Plan the project",))

    assert _hit_ids(pg_session, owner, '"project plan"') == [match.id]


def test_markdown_syntax_and_urls_are_not_searchable(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, blocks=("See [the docs](https://example.com)",))

    assert _hit_ids(pg_session, owner, "docs ") == [match.id]
    assert _hit_ids(pg_session, owner, "example ") == []


@pytest.mark.parametrize("raw", ["' & | ! : * ( ) <-> x", "berlin' | 'x", "a:* & b"])
def test_tsquery_syntax_in_input_is_treated_as_text(
    pg_session: Session, raw: str
) -> None:
    owner = _make_user(pg_session)
    _make_note(pg_session, owner, blocks=("Berlin",))

    search(pg_session, owner, raw)  # must not raise a Postgres syntax error


def test_empty_query_is_rejected(pg_session: Session) -> None:
    owner = _make_user(pg_session)

    with pytest.raises(EmptySearchQueryError):
        search(pg_session, owner, "  ")


# --- Indexing as notes change ---


def test_edited_block_is_searchable_by_its_new_words_only(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    note = _make_note(pg_session, owner)
    node = add_markdown_node(pg_session, note.id, owner, "Berlin", "paragraph")

    update_markdown_node(pg_session, node.id, owner, "Paris", "paragraph", node.version)

    assert _hit_ids(pg_session, owner, "berlin ") == []
    assert _hit_ids(pg_session, owner, "paris ") == [note.id]


def test_deleted_block_is_no_longer_searchable(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    note = _make_note(pg_session, owner, blocks=("Paris",))
    node = add_markdown_node(pg_session, note.id, owner, "Berlin", "paragraph")

    delete_node(pg_session, node.id, owner)

    assert _hit_ids(pg_session, owner, "berlin ") == []


def test_renamed_note_is_searchable_by_its_new_title(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    note = _make_note(pg_session, owner, title="Berlin")

    update_note(pg_session, note.id, owner, title="Paris")

    assert _hit_ids(pg_session, owner, "berlin ") == []
    assert _hit_ids(pg_session, owner, "paris ") == [note.id]


def test_imported_content_is_searchable(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    note = _make_note(pg_session, owner, blocks=("Old",))

    replace_markdown_nodes(pg_session, note.id, owner, [("paragraph", "Berlin")])

    assert _hit_ids(pg_session, owner, "berlin ") == [note.id]
    assert _hit_ids(pg_session, owner, "old ") == []


def test_split_and_merged_text_blocks_stay_searchable(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    note = _make_note(pg_session, owner)
    node = add_text_node(pg_session, note.id, owner, "BerlinParis")

    left, right = split_text_node(pg_session, node.id, owner, 6, node.version)
    assert _hit_ids(pg_session, owner, "paris ") == [note.id]

    merge_text_nodes(pg_session, right.id, owner, left.id, right.version, left.version)
    assert _hit_ids(pg_session, owner, "paris ") == []
    assert _hit_ids(pg_session, owner, "berlinparis ") == [note.id]


def test_attachment_is_searchable_by_file_name(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    note = _make_note(pg_session, owner)
    file = File(
        note_id=note.id, file_name="berlin-map.pdf", state=FileState.COMPLETE.value
    )
    pg_session.add(file)
    pg_session.flush()

    add_attachment_node(pg_session, note.id, owner, file.id)

    assert _hit_ids(pg_session, owner, "map ") == [note.id]


# --- Snippets ---


def _rendered_snippets(hit: SearchHit) -> list[tuple[uuid.UUID, str]]:
    return [
        (
            s.node_id,
            "".join(f"[{g.text}]" if g.highlighted else g.text for g in s.segments),
        )
        for s in hit.snippets
    ]


def test_snippets_are_the_matching_blocks_in_note_order(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    notebook = create_notebook(pg_session, "NB", owner)
    note = create_note(pg_session, notebook_id=notebook.id, owner=owner, title="Trip")
    add_markdown_node(pg_session, note.id, owner, "Groceries", "paragraph")
    budget = add_markdown_node(pg_session, note.id, owner, "The **budget**", "paragraph")
    berlin = add_markdown_node(pg_session, note.id, owner, "# Berlin", "heading")

    [hit] = search(pg_session, owner, "budget berlin ").hits

    assert _rendered_snippets(hit) == [
        (budget.id, "The [budget]"),
        (berlin.id, "[Berlin]"),
    ]


def test_at_most_three_snippets_per_note(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    _make_note(pg_session, owner, blocks=tuple(f"Berlin {i}" for i in range(5)))

    [hit] = search(pg_session, owner, "berlin ").hits

    assert [text for _, text in _rendered_snippets(hit)] == [
        "[Berlin] 0",
        "[Berlin] 1",
        "[Berlin] 2",
    ]


def test_title_is_highlighted(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    _make_note(pg_session, owner, title="Trip to Berlin")

    [hit] = search(pg_session, owner, "berlin ").hits

    assert hit.title_segments == (
        SnippetSegment("Trip to ", highlighted=False),
        SnippetSegment("Berlin", highlighted=True),
    )


def test_title_only_match_shows_the_beginning_of_the_note(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    notebook = create_notebook(pg_session, "NB", owner)
    note = create_note(pg_session, notebook_id=notebook.id, owner=owner, title="Berlin")
    add_markdown_node(pg_session, note.id, owner, "", "paragraph")
    first = add_markdown_node(pg_session, note.id, owner, "Flights *booked*", "paragraph")
    add_markdown_node(pg_session, note.id, owner, "Hotel", "paragraph")

    [hit] = search(pg_session, owner, "berlin ").hits

    assert _rendered_snippets(hit) == [(first.id, "Flights booked")]


def test_empty_note_has_no_snippets(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    _make_note(pg_session, owner, title="Berlin")

    [hit] = search(pg_session, owner, "berlin ").hits

    assert hit.snippets == ()


# --- Ranking and paging ---


def test_title_match_ranks_above_body_match(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    body = _make_note(pg_session, owner, title="Notes", blocks=("Berlin",))
    title = _make_note(pg_session, owner, title="Berlin")
    update_note(pg_session, body.id, owner, title="Notes!")  # most recent

    assert _hit_ids(pg_session, owner, "berlin ") == [title.id, body.id]


def test_sort_by_updated_ignores_relevance(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    body = _make_note(pg_session, owner, title="Notes", blocks=("Berlin",))
    title = _make_note(pg_session, owner, title="Berlin")
    update_note(pg_session, body.id, owner, title="Notes!")

    hits = search(pg_session, owner, "berlin ", sort=SearchSort.UPDATED).hits

    assert [hit.note.id for hit in hits] == [body.id, title.id]


def test_results_are_paged(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    notes = [_make_note(pg_session, owner, title=f"Berlin {i}") for i in range(25)]
    newest_first = [note.id for note in reversed(notes)]

    first = search(pg_session, owner, "berlin")
    second = search(pg_session, owner, "berlin", offset=20, limit=20)

    assert len(first.hits) == DEFAULT_LIMIT
    assert [hit.note.id for hit in second.hits] == newest_first[20:]


# --- Tags ---


def test_tag_only_query_returns_tagged_notes_most_recent_first(
    pg_session: Session,
) -> None:
    owner = _make_user(pg_session)
    older = _make_note(pg_session, owner, title="Older")
    newer = _make_note(pg_session, owner, title="Newer")
    _make_note(pg_session, owner, title="Untagged")
    add_tag_to_note(pg_session, owner, older.id, name="Travel")
    add_tag_to_note(pg_session, owner, newer.id, name="travel")
    update_note(pg_session, newer.id, owner, title="Newer!")

    assert _hit_ids(pg_session, owner, "tag:TRAVEL") == [newer.id, older.id]


def test_tags_and_words_must_all_match(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, blocks=("Berlin",))
    only_one_tag = _make_note(pg_session, owner, blocks=("Berlin",))
    wrong_words = _make_note(pg_session, owner, blocks=("Paris",))
    for note in (match, wrong_words):
        add_tag_to_note(pg_session, owner, note.id, name="travel")
        add_tag_to_note(pg_session, owner, note.id, name="Road Trip")
    add_tag_to_note(pg_session, owner, only_one_tag.id, name="travel")

    assert _hit_ids(pg_session, owner, 'tag:travel tag:"road trip" berlin') == [match.id]


def test_unknown_tag_returns_nothing_and_is_reported(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    note = _make_note(pg_session, owner, blocks=("Berlin",))
    add_tag_to_note(pg_session, owner, note.id, name="travel")

    results = search(pg_session, owner, "tag:travel tag:Work berlin")

    assert results.hits == []
    assert results.unknown_tags == ["work"]


def test_other_users_tags_on_a_shared_note_do_not_apply(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    friend = _make_user(pg_session, "friend@test.com")
    note = _make_note(pg_session, owner, blocks=("Berlin",))
    grant_entitlement(
        pg_session,
        owner,
        note_id=note.id,
        grantee_email=friend.email,
        role_name=RoleName.NOTE_VIEWER,
    )
    find_or_create_tag(pg_session, friend, "travel")
    add_tag_to_note(pg_session, owner, note.id, name="travel")

    assert _hit_ids(pg_session, friend, "tag:travel") == []


# --- Visibility ---


def test_other_users_notes_are_not_found(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    stranger = _make_user(pg_session, "stranger@test.com")
    _make_note(pg_session, owner, blocks=("Berlin",))

    assert _hit_ids(pg_session, stranger, "berlin") == []


def test_note_shared_with_caller_is_found(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    friend = _make_user(pg_session, "friend@test.com")
    note = _make_note(pg_session, owner, blocks=("Berlin",))
    grant_entitlement(
        pg_session,
        owner,
        note_id=note.id,
        grantee_email=friend.email,
        role_name=RoleName.NOTE_VIEWER,
    )

    assert _hit_ids(pg_session, friend, "berlin") == [note.id]


def test_notes_in_notebook_shared_with_caller_are_found(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    friend = _make_user(pg_session, "friend@test.com")
    note = _make_note(pg_session, owner, blocks=("Berlin",))
    grant_entitlement(
        pg_session,
        owner,
        notebook_id=note.notebook_id,
        grantee_email=friend.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )

    assert _hit_ids(pg_session, friend, "berlin") == [note.id]


def test_notebook_permission_to_only_list_notes_does_not_expose_content(
    pg_session: Session,
) -> None:
    owner = _make_user(pg_session)
    friend = _make_user(pg_session, "friend@test.com")
    note = _make_note(pg_session, owner, blocks=("Berlin",))
    # No role grants list_notes without view_notes; only a direct
    # permission entitlement can.
    pg_session.add(
        Entitlement(
            principal_id=friend.uid,
            notebook_id=note.notebook_id,
            permission_name=PermissionName.LIST_NOTES.value,
        ),
    )
    pg_session.flush()

    assert _hit_ids(pg_session, friend, "berlin") == []
