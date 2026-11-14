"""Tests for the blog post endpoints (against Postgres, for the embeddings)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from assistant.blogs.chunking import PostChunk
from assistant.blogs.service import MAX_BULK_POSTS
from assistant.blogs.store import post_chunk_embedding, replace_post_chunks
from assistant.models.schema import (
    BlogEmbedStatus,
    BlogPost,
    BlogPostState,
    BlogPostStatus,
    BlogSource,
    BlogSourceKind,
    Category,
    Tag,
    User,
)
from assistant.notes.tags import find_or_create_tag
from assistant.vectors.store import EMBEDDING_DIMENSIONS
from tests.api.conftest import make_auth_headers

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)
Headers = dict[str, str]


@pytest.fixture
def owner(pg_session: Session) -> User:
    user = User(email="owner@example.com", firstname="O", lastname="W")
    pg_session.add(user)
    pg_session.flush()
    return user


@pytest.fixture
def stranger(pg_session: Session) -> User:
    user = User(email="stranger@example.com", firstname="S", lastname="T")
    pg_session.add(user)
    pg_session.flush()
    return user


@pytest.fixture
def headers(owner: User) -> Headers:
    return make_auth_headers(owner.uid)


@pytest.fixture
def stranger_headers(stranger: User) -> Headers:
    return make_auth_headers(stranger.uid)


def _source(
    session: Session,
    owner: User,
    *,
    category: Category | None = None,
    **fields: object,
) -> BlogSource:
    source = BlogSource(
        owner_id=owner.uid,
        category_id=category.id if category else None,
        url="https://blog.example.com",
        feed_url=f"https://blog.example.com/{uuid.uuid4()}.xml",
        kind=BlogSourceKind.FEED.value,
        title="Blog",
        collect_since=NOW - timedelta(days=7),
        **fields,
    )
    session.add(source)
    session.flush()
    return source


def _post(
    session: Session,
    source: BlogSource,
    *,
    age: int = 0,
    status: BlogPostStatus = BlogPostStatus.PROCESSED,
    state: BlogPostState = BlogPostState.NEW,
    **fields: object,
) -> BlogPost:
    key = uuid.uuid4().hex
    post = BlogPost(
        source_id=source.id,
        post_key=key,
        url=f"https://blog.example.com/{key}",
        title=fields.pop("title", "A post"),
        summary=fields.pop("summary", "A summary."),
        published_at=NOW - timedelta(hours=age),
        status=status.value,
        state=state.value,
        **fields,
    )
    session.add(post)
    session.flush()
    return post


def _embed(session: Session, source: BlogSource, post: BlogPost) -> None:
    replace_post_chunks(
        session,
        post_id=post.id,
        source_id=source.id,
        owner_id=source.owner_id,
        chunks=[PostChunk(index=0, text="text", metadata={})],
        embeddings=[[0.1] * EMBEDDING_DIMENSIONS],
    )
    post.embed_status = BlogEmbedStatus.DONE.value
    session.flush()


def _chunk_count(session: Session, post: BlogPost) -> int:
    stmt = (
        select(func.count())
        .select_from(post_chunk_embedding)
        .where(post_chunk_embedding.c.post_id == post.id)
    )
    return session.scalar(stmt) or 0


def _list(client: TestClient, headers: Headers, **params: object) -> dict:
    response = client.get("/blog/post", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _ids(client: TestClient, headers: Headers, **params: object) -> list[str]:
    return [post["id"] for post in _list(client, headers, **params)["posts"]]


def _set_state(client: TestClient, headers: Headers, post: BlogPost, state: str) -> dict:
    response = client.patch(
        f"/blog/post/{post.id}", json={"state": state}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Views ---


def test_requires_authentication(pg_client: TestClient) -> None:
    assert pg_client.get("/blog/post").status_code == 401


def test_all_is_newest_first_with_card_fields(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    older = _post(pg_session, source, age=5)
    newer = _post(pg_session, source, age=1, match_level="high", motivation="Because.")

    body = _list(pg_client, headers)

    assert [post["id"] for post in body["posts"]] == [str(newer.id), str(older.id)]
    card = body["posts"][0]
    assert card["source_title"] == "Blog"
    assert card["title"] == "A post"
    assert card["summary"] == "A summary."
    assert card["match_level"] == "high"
    assert card["motivation"] == "Because."
    assert card["state"] == "new"
    assert card["tags"] == []
    assert body["next_cursor"] is None


def test_waiting_and_skipped_posts_are_hidden(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    _post(pg_session, source, status=BlogPostStatus.PENDING)
    _post(pg_session, source, status=BlogPostStatus.SKIPPED)
    assert _ids(pg_client, headers) == []


def test_failed_posts_are_shown(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    post = _post(pg_session, source, status=BlogPostStatus.FAILED, summary=None)
    [card] = _list(pg_client, headers)["posts"]
    assert card["id"] == str(post.id)
    assert card["status"] == "failed"
    assert card["summary"] is None


def test_relevant_is_only_what_the_user_marked_useful(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    useful = _post(pg_session, source, state=BlogPostState.USEFUL, match_level="low")
    _post(pg_session, source, match_level="high")
    _post(pg_session, source, state=BlogPostState.NOT_USEFUL, match_level="high")
    assert _ids(pg_client, headers, view="relevant") == [str(useful.id)]


def test_a_low_match_never_hides_a_post(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    post = _post(pg_session, source, match_level="low")
    assert _ids(pg_client, headers) == [str(post.id)]
    assert _ids(pg_client, headers, view="new") == [str(post.id)]


def test_new_is_sorted_by_match_then_newest(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    unscored = _post(pg_session, source, age=0)
    low = _post(pg_session, source, age=1, match_level="low")
    high_old = _post(pg_session, source, age=9, match_level="high")
    high_new = _post(pg_session, source, age=8, match_level="high")
    medium = _post(pg_session, source, age=2, match_level="medium")
    _post(pg_session, source, state=BlogPostState.USEFUL, match_level="high")

    assert _ids(pg_client, headers, view="new") == [
        str(post.id) for post in (high_new, high_old, medium, low, unscored)
    ]


def test_someone_elses_posts_are_not_listed(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    stranger_headers: Headers,
) -> None:
    _post(pg_session, _source(pg_session, owner))
    assert _ids(pg_client, stranger_headers) == []


def test_two_users_collect_separately(  # noqa: PLR0913
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    stranger: User,
    headers: Headers,
    stranger_headers: Headers,
) -> None:
    mine = _post(pg_session, _source(pg_session, owner))
    theirs = _post(pg_session, _source(pg_session, stranger))
    assert _ids(pg_client, headers) == [str(mine.id)]
    assert _ids(pg_client, stranger_headers) == [str(theirs.id)]


# --- Filters ---


def test_filter_by_category_and_unfiled(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    category = Category(owner_id=owner.uid, name="Tech")
    pg_session.add(category)
    pg_session.flush()
    filed = _post(pg_session, _source(pg_session, owner, category=category))
    unfiled = _post(pg_session, _source(pg_session, owner))

    assert _ids(pg_client, headers, category_id=category.id) == [str(filed.id)]
    assert _ids(pg_client, headers, unfiled=True) == [str(unfiled.id)]


def test_category_filter_applies_to_new(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    category = Category(owner_id=owner.uid, name="Tech")
    pg_session.add(category)
    pg_session.flush()
    filed = _post(pg_session, _source(pg_session, owner, category=category))
    _post(pg_session, _source(pg_session, owner))
    assert _ids(pg_client, headers, view="new", category_id=category.id) == [
        str(filed.id)
    ]


def test_filter_by_tag(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    tagged = _post(pg_session, source)
    _post(pg_session, source)
    added = pg_client.post(
        f"/blog/post/{tagged.id}/tag", json={"name": "keep"}, headers=headers
    ).json()
    assert _ids(pg_client, headers, tag=added[0]["id"]) == [str(tagged.id)]


def test_filter_by_archived_source(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    archived = _source(pg_session, owner, archived_at=NOW, enabled=False)
    kept = _post(pg_session, archived, state=BlogPostState.USEFUL)
    _post(pg_session, _source(pg_session, owner))
    assert _ids(pg_client, headers, source_id=archived.id) == [str(kept.id)]


def test_archived_useful_posts_show_their_source_name(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    archived = _source(pg_session, owner, archived_at=NOW, enabled=False)
    _post(pg_session, archived, state=BlogPostState.USEFUL)
    [card] = _list(pg_client, headers, view="relevant")["posts"]
    assert card["source_title"] == "Blog"


def test_category_and_unfiled_together_are_refused(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    category = Category(owner_id=owner.uid, name="Tech")
    pg_session.add(category)
    pg_session.flush()
    response = pg_client.get(
        "/blog/post",
        params={"category_id": category.id, "unfiled": True},
        headers=headers,
    )
    assert response.status_code == 422


def test_someone_elses_filters_are_not_found(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    stranger: User,
    stranger_headers: Headers,
) -> None:
    category = Category(owner_id=owner.uid, name="Tech")
    pg_session.add(category)
    source = _source(pg_session, owner)
    tag, _ = find_or_create_tag(pg_session, owner, "mine")
    pg_session.flush()
    assert stranger.uid != owner.uid
    for params in (
        {"category_id": category.id},
        {"source_id": source.id},
        {"tag": tag.id},
    ):
        response = pg_client.get("/blog/post", params=params, headers=stranger_headers)
        assert response.status_code == 404, params


# --- Paging ---


def test_pages_cover_everything_once(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    posts = [_post(pg_session, source, age=age) for age in range(5)]

    seen: list[str] = []
    cursor = None
    for _ in range(5):
        params: dict[str, object] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        body = _list(pg_client, headers, **params)
        seen += [post["id"] for post in body["posts"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == [str(post.id) for post in posts]


def test_ties_on_date_are_broken_by_id(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    posts = [_post(pg_session, source, age=1) for _ in range(4)]
    first = _list(pg_client, headers, limit=2)
    second = _list(pg_client, headers, limit=2, cursor=first["next_cursor"])
    ids = [post["id"] for post in first["posts"] + second["posts"]]
    assert sorted(ids) == sorted(str(post.id) for post in posts)


def test_evaluated_posts_leaving_the_list_skip_nothing(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    posts = [_post(pg_session, source, age=age) for age in range(4)]

    first = _list(pg_client, headers, view="new", limit=2)
    for card in first["posts"]:
        pg_client.patch(
            f"/blog/post/{card['id']}", json={"state": "not_useful"}, headers=headers
        )
    second = _list(pg_client, headers, view="new", limit=2, cursor=first["next_cursor"])

    assert [card["id"] for card in second["posts"]] == [str(p.id) for p in posts[2:]]


def test_new_pages_across_match_levels(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    expected = [
        _post(pg_session, source, age=5, match_level="high"),
        _post(pg_session, source, age=6, match_level="medium"),
        _post(pg_session, source, age=1, match_level="low"),
        _post(pg_session, source, age=0),
    ]
    seen: list[str] = []
    cursor = None
    for _ in range(4):
        params: dict[str, object] = {"limit": 1, "view": "new"}
        if cursor:
            params["cursor"] = cursor
        body = _list(pg_client, headers, **params)
        seen += [post["id"] for post in body["posts"]]
        cursor = body["next_cursor"]
    assert seen == [str(post.id) for post in expected]
    assert cursor is None


@pytest.mark.parametrize(
    "cursor", ["garbage", "e30=", "WzEsIDJd", "WyJub3QtYS1kYXRlIiwgIngiXQ=="]
)
def test_bad_cursor_is_refused(
    pg_client: TestClient, owner: User, headers: Headers, cursor: str
) -> None:
    assert owner
    response = pg_client.get("/blog/post", params={"cursor": cursor}, headers=headers)
    assert response.status_code == 422


def test_cursor_of_another_view_is_refused(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    _post(pg_session, source, age=1)
    _post(pg_session, source, age=2)
    cursor = _list(pg_client, headers, limit=1)["next_cursor"]
    response = pg_client.get(
        "/blog/post", params={"cursor": cursor, "view": "new"}, headers=headers
    )
    assert response.status_code == 422


# --- Verdicts ---


def test_marking_useful_requests_embeddings(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    card = _set_state(pg_client, headers, post, "useful")
    assert card["state"] == "useful"
    assert card["evaluated_at"] is not None
    pg_session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.PENDING.value


def test_not_useful_requests_no_embeddings(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    _set_state(pg_client, headers, post, "not_useful")
    pg_session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.NONE.value


@pytest.mark.parametrize("target", ["not_useful", "new"])
def test_leaving_useful_deletes_the_embeddings(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    headers: Headers,
    target: str,
) -> None:
    source = _source(pg_session, owner)
    post = _post(pg_session, source, state=BlogPostState.USEFUL)
    _embed(pg_session, source, post)

    _set_state(pg_client, headers, post, target)

    assert _chunk_count(pg_session, post) == 0
    pg_session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.NONE.value


def test_setting_useful_twice_keeps_the_embeddings(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    post = _post(pg_session, source, state=BlogPostState.USEFUL)
    _embed(pg_session, source, post)
    _set_state(pg_client, headers, post, "useful")
    assert _chunk_count(pg_session, post) == 1
    pg_session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.DONE.value


def test_undo_clears_the_evaluation_time(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    _set_state(pg_client, headers, post, "not_useful")
    card = _set_state(pg_client, headers, post, "new")
    assert card["state"] == "new"
    assert card["evaluated_at"] is None


def test_a_verdict_can_change_from_any_state(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    for state in ("useful", "not_useful", "useful", "new"):
        assert _set_state(pg_client, headers, post, state)["state"] == state


def test_unknown_state_is_refused(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    response = pg_client.patch(
        f"/blog/post/{post.id}", json={"state": "maybe"}, headers=headers
    )
    assert response.status_code == 422


def test_someone_elses_post_is_not_found(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    stranger_headers: Headers,
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    response = pg_client.patch(
        f"/blog/post/{post.id}", json={"state": "useful"}, headers=stranger_headers
    )
    assert response.status_code == 404


@pytest.mark.parametrize("status", [BlogPostStatus.PENDING, BlogPostStatus.SKIPPED])
def test_hidden_posts_cannot_be_evaluated(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    headers: Headers,
    status: BlogPostStatus,
) -> None:
    post = _post(pg_session, _source(pg_session, owner), status=status)
    response = pg_client.patch(
        f"/blog/post/{post.id}", json={"state": "useful"}, headers=headers
    )
    assert response.status_code == 404


# --- Read ---


def _set_read(client: TestClient, headers: Headers, post: BlogPost, read: bool) -> dict:
    response = client.put(
        f"/blog/post/{post.id}/read", json={"read": read}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_posts_start_unread(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    _post(pg_session, _source(pg_session, owner))
    [card] = _list(pg_client, headers)["posts"]
    assert card["read_at"] is None


def test_marking_read_keeps_the_verdict(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner), state=BlogPostState.USEFUL)
    card = _set_read(pg_client, headers, post, True)
    assert card["read_at"] is not None
    assert card["state"] == "useful"
    pg_session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.NONE.value


def test_marking_read_twice_keeps_the_first_time(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    first = _set_read(pg_client, headers, post, True)["read_at"]
    assert _set_read(pg_client, headers, post, True)["read_at"] == first


def test_marking_unread_clears_the_read_time(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    _set_read(pg_client, headers, post, True)
    assert _set_read(pg_client, headers, post, False)["read_at"] is None


def test_filter_by_read(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    read = _post(pg_session, source, state=BlogPostState.USEFUL, age=1)
    to_read = _post(pg_session, source, state=BlogPostState.USEFUL, age=2)
    _set_read(pg_client, headers, read, True)

    assert _ids(pg_client, headers, view="relevant", read=True) == [str(read.id)]
    assert _ids(pg_client, headers, view="relevant", read=False) == [str(to_read.id)]
    assert _ids(pg_client, headers, view="relevant") == [str(read.id), str(to_read.id)]


def test_someone_elses_post_cannot_be_marked_read(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    stranger_headers: Headers,
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    response = pg_client.put(
        f"/blog/post/{post.id}/read", json={"read": True}, headers=stranger_headers
    )
    assert response.status_code == 404


def test_hidden_posts_cannot_be_marked_read(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner), status=BlogPostStatus.PENDING)
    response = pg_client.put(
        f"/blog/post/{post.id}/read", json={"read": True}, headers=headers
    )
    assert response.status_code == 404


# --- Bulk ---


def test_bulk_changes_only_the_listed_posts(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    listed = [_post(pg_session, source), _post(pg_session, source)]
    other = _post(pg_session, source)
    response = pg_client.post(
        "/blog/post/bulk-state",
        json={"post_ids": [str(p.id) for p in listed], "state": "not_useful"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"updated": 2}
    pg_session.expire_all()
    assert {post.state for post in listed} == {"not_useful"}
    assert other.state == "new"


def test_bulk_with_someone_elses_post_changes_nothing(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    stranger: User,
    headers: Headers,
) -> None:
    mine = _post(pg_session, _source(pg_session, owner))
    theirs = _post(pg_session, _source(pg_session, stranger))
    response = pg_client.post(
        "/blog/post/bulk-state",
        json={"post_ids": [str(mine.id), str(theirs.id)], "state": "not_useful"},
        headers=headers,
    )
    assert response.status_code == 404
    pg_session.expire_all()
    assert mine.state == "new"


def test_bulk_limit(pg_client: TestClient, owner: User, headers: Headers) -> None:
    assert owner
    too_many = [str(uuid.uuid4()) for _ in range(MAX_BULK_POSTS + 1)]
    for ids in (too_many, []):
        response = pg_client.post(
            "/blog/post/bulk-state",
            json={"post_ids": ids, "state": "not_useful"},
            headers=headers,
        )
        assert response.status_code == 422


def test_bulk_leaving_useful_deletes_embeddings(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    source = _source(pg_session, owner)
    post = _post(pg_session, source, state=BlogPostState.USEFUL)
    _embed(pg_session, source, post)
    pg_client.post(
        "/blog/post/bulk-state",
        json={"post_ids": [str(post.id)], "state": "not_useful"},
        headers=headers,
    )
    assert _chunk_count(pg_session, post) == 0


# --- Tags ---


def test_tag_by_name_creates_it_in_the_shared_vocabulary(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    tags = pg_client.post(
        f"/blog/post/{post.id}/tag", json={"name": "Keep"}, headers=headers
    ).json()
    assert [tag["name"] for tag in tags] == ["Keep"]
    vocabulary = pg_client.get("/tag", headers=headers).json()
    assert [tag["name"] for tag in vocabulary] == ["Keep"]
    [card] = _list(pg_client, headers)["posts"]
    assert [tag["name"] for tag in card["tags"]] == ["Keep"]


def test_tag_by_id_is_idempotent(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    tag, _ = find_or_create_tag(pg_session, owner, "existing")
    pg_session.flush()
    for _ in range(2):
        tags = pg_client.post(
            f"/blog/post/{post.id}/tag", json={"tag_id": str(tag.id)}, headers=headers
        ).json()
    assert [t["id"] for t in tags] == [str(tag.id)]


def test_untag_keeps_the_tag(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    [tag] = pg_client.post(
        f"/blog/post/{post.id}/tag", json={"name": "keep"}, headers=headers
    ).json()
    for _ in range(2):
        response = pg_client.delete(
            f"/blog/post/{post.id}/tag/{tag['id']}", headers=headers
        )
        assert response.status_code == 204
    assert _list(pg_client, headers)["posts"][0]["tags"] == []
    assert pg_session.get(Tag, uuid.UUID(tag["id"])) is not None


def test_tags_only_reach_the_owners_posts(  # noqa: PLR0913
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
    stranger: User,
    headers: Headers,
    stranger_headers: Headers,
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    theirs, _ = find_or_create_tag(pg_session, stranger, "theirs")
    pg_session.flush()

    their_attempt = pg_client.post(
        f"/blog/post/{post.id}/tag", json={"name": "x"}, headers=stranger_headers
    )
    assert their_attempt.status_code == 404
    with_their_tag = pg_client.post(
        f"/blog/post/{post.id}/tag", json={"tag_id": str(theirs.id)}, headers=headers
    )
    assert with_their_tag.status_code == 404
    removal = pg_client.delete(
        f"/blog/post/{post.id}/tag/{theirs.id}", headers=stranger_headers
    )
    assert removal.status_code == 404


def test_tag_needs_exactly_one_of_id_or_name(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    post = _post(pg_session, _source(pg_session, owner))
    response = pg_client.post(f"/blog/post/{post.id}/tag", json={}, headers=headers)
    assert response.status_code == 422


def test_a_tag_filter_works_with_a_tag_from_notes(
    pg_client: TestClient, pg_session: Session, owner: User, headers: Headers
) -> None:
    tag, _ = find_or_create_tag(pg_session, owner, "shared")
    pg_session.flush()
    post = _post(pg_session, _source(pg_session, owner))
    pg_client.post(
        f"/blog/post/{post.id}/tag", json={"tag_id": str(tag.id)}, headers=headers
    )
    assert _ids(pg_client, headers, tag=tag.id) == [str(post.id)]
