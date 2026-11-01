"""Tests for the safe fetcher. Nothing here touches the network."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from assistant.blogs import fetch as fetch_module
from assistant.blogs.exceptions import BlockedUrlError, FetchError
from assistant.blogs.fetch import (
    MAX_BYTES,
    MAX_REDIRECTS,
    fetch,
    is_public_address,
    resolve_host,
)

PUBLIC_IP = "93.184.216.34"
PUBLIC_IP6 = "2606:2800:220:1:248:1893:25c8:1946"


def _dns(*addresses: str) -> list[tuple[Any, ...]]:
    infos: list[tuple[Any, ...]] = []
    for address in addresses:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        infos.append((family, socket.SOCK_STREAM, 6, "", (address, 443)))
    return infos


def _response(
    status: int = 200,
    body: bytes = b"ok",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.headers = headers or {}
    response.iter_content.return_value = [body]
    response.__enter__.return_value = response
    return response


@pytest.fixture
def dns() -> Iterator[MagicMock]:
    with patch.object(fetch_module.socket, "getaddrinfo") as getaddrinfo:
        getaddrinfo.return_value = _dns(PUBLIC_IP)
        yield getaddrinfo


@pytest.fixture
def http() -> Iterator[MagicMock]:
    with patch.object(fetch_module.requests.Session, "get") as get:
        get.return_value = _response()
        yield get


# --- Address classes ---


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "::1",
        "10.0.0.1",  # private
        "172.16.0.1",
        "192.168.1.1",
        "fd00::1",
        "169.254.169.254",  # link-local, cloud metadata
        "fe80::1",
        "224.0.0.1",  # multicast
        "ff02::1",
        "240.0.0.1",  # reserved
        "0.0.0.0",
        "100.64.0.1",  # shared
        "::ffff:127.0.0.1",  # the same, wrapped in IPv6
        "::ffff:10.0.0.1",
        "2002:7f00:1::",  # 6to4 of 127.0.0.1
        "64:ff9b::7f00:1",  # NAT64 of 127.0.0.1
    ],
)
def test_non_public_addresses_are_refused(address: str) -> None:
    assert not is_public_address(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", [PUBLIC_IP, PUBLIC_IP6, "::ffff:93.184.216.34"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert is_public_address(ipaddress.ip_address(address))


def test_one_private_answer_blocks_the_host(dns: MagicMock) -> None:
    dns.return_value = _dns(PUBLIC_IP, "10.0.0.1")
    with pytest.raises(BlockedUrlError):
        resolve_host("example.com", 443)


def test_unresolvable_host(dns: MagicMock) -> None:
    dns.side_effect = socket.gaierror
    with pytest.raises(FetchError):
        resolve_host("nope.example", 443)


# --- URLs ---


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/",
        "https://user:secret@example.com/",
        "https://user@example.com/",
        "http://",
        "http://example.com:notaport/",
        "not a url",
    ],
)
def test_bad_urls_are_refused(url: str, dns: MagicMock, http: MagicMock) -> None:
    with pytest.raises(BlockedUrlError):
        fetch(url)
    http.assert_not_called()
    dns.assert_not_called()


def test_literal_private_ip_is_refused(http: MagicMock) -> None:
    with pytest.raises(BlockedUrlError):
        fetch("http://127.0.0.1:8000/")
    http.assert_not_called()


# --- Pinning ---


def test_connects_to_the_validated_address(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    result = fetch("https://example.com/feed?x=1#frag")
    url = http.call_args.args[0]
    assert url == f"https://{PUBLIC_IP}:443/feed?x=1"
    assert http.call_args.kwargs["headers"]["Host"] == "example.com"
    assert http.call_args.kwargs["allow_redirects"] is False
    assert result.url == "https://example.com/feed?x=1#frag"


def test_host_header_keeps_a_custom_port(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    fetch("http://example.com:8080/")
    assert http.call_args.args[0] == f"http://{PUBLIC_IP}:8080/"
    assert http.call_args.kwargs["headers"]["Host"] == "example.com:8080"


def test_ipv6_addresses_are_bracketed(dns: MagicMock, http: MagicMock) -> None:
    dns.return_value = _dns(PUBLIC_IP6)
    fetch("https://example.com/")
    assert http.call_args.args[0] == f"https://[{PUBLIC_IP6}]:443/"


def test_next_address_is_tried_when_one_does_not_connect(
    dns: MagicMock, http: MagicMock
) -> None:
    dns.return_value = _dns(PUBLIC_IP6, PUBLIC_IP)
    http.side_effect = [requests.ConnectionError(), _response()]
    assert fetch("https://example.com/").status == 200
    assert http.call_args.args[0] == f"https://{PUBLIC_IP}:443/"


def test_connection_failure_on_every_address(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    http.side_effect = requests.ConnectionError()
    with pytest.raises(FetchError, match="Could not reach"):
        fetch("https://example.com/")


def test_tls_is_verified_against_the_host_name() -> None:
    adapter = fetch_module._PinnedAdapter("example.com")
    assert adapter.poolmanager.connection_pool_kw["server_hostname"] == "example.com"
    assert adapter.poolmanager.connection_pool_kw["assert_hostname"] == "example.com"


# --- Redirects ---


def test_follows_a_redirect_and_resolves_it_relatively(
    dns: MagicMock,  # noqa: ARG001
    http: MagicMock,
) -> None:
    http.side_effect = [
        _response(301, headers={"Location": "/new"}),
        _response(body=b"landed"),
    ]
    result = fetch("https://example.com/old")
    assert result.url == "https://example.com/new"
    assert result.content == b"landed"


def test_redirect_to_a_private_address_is_refused(
    dns: MagicMock, http: MagicMock
) -> None:
    dns.side_effect = [_dns(PUBLIC_IP), _dns("169.254.169.254")]
    http.return_value = _response(302, headers={"Location": "http://rebind.example/"})
    with pytest.raises(BlockedUrlError):
        fetch("https://example.com/")
    assert http.call_count == 1


def test_redirect_to_a_private_literal_is_refused(
    dns: MagicMock, http: MagicMock
) -> None:
    dns.side_effect = [_dns(PUBLIC_IP), _dns("127.0.0.1")]
    http.return_value = _response(302, headers={"Location": "http://127.0.0.1/admin"})
    with pytest.raises(BlockedUrlError):
        fetch("https://example.com/")


def test_redirect_to_another_scheme_is_refused(
    dns: MagicMock,  # noqa: ARG001
    http: MagicMock,
) -> None:
    http.return_value = _response(302, headers={"Location": "file:///etc/passwd"})
    with pytest.raises(BlockedUrlError):
        fetch("https://example.com/")


def test_too_many_redirects(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    http.return_value = _response(302, headers={"Location": "/again"})
    with pytest.raises(FetchError, match="redirects"):
        fetch("https://example.com/")
    assert http.call_count == MAX_REDIRECTS + 1


# --- Limits ---


def test_stops_past_the_size_limit(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    response = _response()
    chunk = b"x" * (1024 * 1024)
    response.iter_content.return_value = iter(lambda: chunk, None)
    http.return_value = response
    with pytest.raises(FetchError, match="too large"):
        fetch("https://example.com/huge")


def test_exactly_the_size_limit_is_fine(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    http.return_value = _response(body=b"x" * MAX_BYTES)
    assert len(fetch("https://example.com/").content) == MAX_BYTES


def test_a_slow_drip_hits_the_total_deadline(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    response = _response()
    response.iter_content.return_value = iter(lambda: b"x", None)
    http.return_value = response
    clock = iter(range(0, 1000, 5))
    with (
        patch.object(fetch_module.time, "monotonic", lambda: next(clock)),
        pytest.raises(FetchError, match="too long"),
    ):
        fetch("https://example.com/slow")


def test_timeout_is_passed_on(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    fetch("https://example.com/")
    assert http.call_args.kwargs["timeout"] == fetch_module.TIMEOUT_SECONDS


def test_read_timeout_is_a_fetch_error(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    http.side_effect = requests.ReadTimeout()
    with pytest.raises(FetchError, match="Could not reach"):
        fetch("https://example.com/")


# --- Conditional GET and headers ---


def test_sends_validators_and_user_agent(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    fetch("https://example.com/", etag='"abc"', last_modified="yesterday")
    headers = http.call_args.kwargs["headers"]
    assert headers["If-None-Match"] == '"abc"'
    assert headers["If-Modified-Since"] == "yesterday"
    assert "AssistantBlogCollector" in headers["User-Agent"]


def test_not_modified(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    http.return_value = _response(304, b"")
    result = fetch("https://example.com/")
    assert result.not_modified
    result.raise_for_status()


def test_reads_validators_from_the_response(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    http.return_value = _response(
        headers={"ETag": '"v2"', "Last-Modified": "Sat, 01 Jan 2028 00:00:00 GMT"}
    )
    result = fetch("https://example.com/")
    assert result.etag == '"v2"'
    assert result.last_modified == "Sat, 01 Jan 2028 00:00:00 GMT"


def test_error_status_has_no_response_content(dns: MagicMock, http: MagicMock) -> None:  # noqa: ARG001
    http.return_value = _response(500, b"secret stack trace")
    result = fetch("https://example.com/")
    assert not result.ok
    with pytest.raises(FetchError) as caught:
        result.raise_for_status()
    assert "secret" not in str(caught.value)
