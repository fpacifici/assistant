"""Tests for post identity."""

from __future__ import annotations

from assistant.blogs.identity import canonical_path, post_key

# --- Without a guid ---


def test_domain_move_keeps_the_key() -> None:
    assert post_key("https://old.example.com/2024/hello/") == post_key(
        "http://new.example.org/2024/hello"
    )


def test_different_paths_differ() -> None:
    assert post_key("https://a.example/one") != post_key("https://a.example/two")


def test_identifying_query_is_kept() -> None:
    assert post_key("https://a.example/?p=123") != post_key("https://a.example/?p=124")


def test_tracking_query_is_dropped() -> None:
    assert post_key("https://a.example/post?utm_source=rss&utm_medium=feed") == post_key(
        "https://a.example/post"
    )
    assert post_key("https://a.example/post?fbclid=x&ref=hn") == post_key(
        "https://a.example/post"
    )


def test_tracking_is_dropped_next_to_an_identifying_parameter() -> None:
    assert post_key("https://a.example/?utm_campaign=c&p=9") == post_key(
        "https://a.example/?p=9"
    )


def test_query_order_and_fragment_do_not_matter() -> None:
    assert canonical_path("https://a.example/x?b=2&a=1#top") == "/x?a=1&b=2"


# --- With a guid ---


def test_opaque_guid_identifies_the_post() -> None:
    guid = "tag:blog.example.com,2024:post-1"
    assert post_key("https://a.example/one", guid) == post_key(
        "https://b.example/renamed", guid
    )
    assert post_key("https://a.example/one", guid) != post_key(
        "https://a.example/one", "tag:blog.example.com,2024:post-2"
    )


def test_guid_that_is_a_url_uses_its_path() -> None:
    assert post_key(
        "https://feeds.example/redirect/abc", "https://old.example/2024/hello/"
    ) == post_key("https://new.example/2024/hello")


def test_blank_guid_counts_as_none() -> None:
    assert post_key("https://a.example/one", "  ") == post_key("https://a.example/one")
