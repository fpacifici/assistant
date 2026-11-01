"""The safe fetcher, the only code in the blogs package that opens a URL.

URLs come from users and from fetched content, so every request is treated
as hostile (SSRF, oversized or endless responses):

- Only `http` and `https`, and no credentials in the URL.
- The host is resolved, every address must be public, and the connection goes
  to one of the validated addresses, so a second DNS answer can't change the
  target. TLS is still verified against the host name.
- Redirects are followed here, at most `MAX_REDIRECTS`, with the same checks
  on every hop.
- A whole request is limited to `TIMEOUT_SECONDS` and `MAX_BYTES`. The limit
  applies to decompressed bytes, so a small gzip bomb stops too.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter

from assistant.blogs.exceptions import BlockedUrlError, FetchError

if TYPE_CHECKING:
    from typing import Any

MAX_REDIRECTS = 5
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 10
USER_AGENT = "AssistantBlogCollector/1.0 (+https://github.com/fpacifici/assistant)"

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_CHUNK_BYTES = 64 * 1024
_HTTP_BAD_REQUEST = 400
_HTTP_NOT_MODIFIED = 304
# RFC 6052 NAT64 prefix: the last 32 bits are an IPv4 address.
_NAT64 = ipaddress.ip_network("64:ff9b::/96")

type _Address = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A finished request.

    Attributes:
        url: The final URL, after redirects.
        status: The final HTTP status. Anything is possible except a redirect.
        content: The decompressed body, at most `MAX_BYTES`.
        etag: The `ETag` header, if any.
        last_modified: The `Last-Modified` header, if any.
    """

    url: str
    status: int
    content: bytes
    etag: str | None = None
    last_modified: str | None = None

    @property
    def not_modified(self) -> bool:
        """Whether a conditional request found nothing new."""
        return self.status == _HTTP_NOT_MODIFIED

    @property
    def ok(self) -> bool:
        """Whether the request succeeded (a 304 counts)."""
        return self.status < _HTTP_BAD_REQUEST

    def raise_for_status(self) -> None:
        """Raise unless the request succeeded.

        Raises:
            FetchError: On a 4xx or 5xx.
        """
        if not self.ok:
            msg = f"The server answered HTTP {self.status}"
            raise FetchError(msg)


def _embedded_ipv4(address: _Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 transition address reaches, if any."""
    if isinstance(address, ipaddress.IPv4Address):
        return None
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    if address.teredo is not None:
        return address.teredo[1]
    if address in _NAT64:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def is_public_address(address: _Address) -> bool:
    """Whether an address can be fetched.

    `is_global` already excludes loopback, private, link-local, reserved,
    shared (CGNAT) and documentation ranges, but not multicast.
    """
    embedded = _embedded_ipv4(address)
    target = embedded if embedded is not None else address
    return target.is_global and not target.is_multicast


def resolve_host(host: str, port: int) -> list[str]:
    """Resolve a host and return its addresses, all checked as public.

    Rejects the host if any address is not public, since which one a client
    would pick is not ours to know.

    Raises:
        BlockedUrlError: If the host has a non-public address.
        FetchError: If it does not resolve.
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        msg = "Could not resolve the host"
        raise FetchError(msg) from exc
    addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        msg = "Could not resolve the host"
        raise FetchError(msg)
    for raw in addresses:
        # Strip an IPv6 zone id: such an address is link-local anyway.
        if not is_public_address(ipaddress.ip_address(raw.split("%", maxsplit=1)[0])):
            msg = "This address is not allowed"
            raise BlockedUrlError(msg)
    return addresses


class _PinnedAdapter(HTTPAdapter):
    """Sends a request whose URL names an IP, verifying TLS for the host name."""

    def __init__(self, hostname: str) -> None:
        self._hostname = hostname
        super().__init__(max_retries=0)

    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: Any,  # noqa: ANN401
    ) -> None:
        super().init_poolmanager(
            connections,
            maxsize,
            block=block,
            server_hostname=self._hostname,
            assert_hostname=self._hostname,
            **pool_kwargs,
        )


def _checked_parts(url: str) -> tuple[str, str, int]:
    """Validate a URL and return (scheme, host, port).

    Raises:
        BlockedUrlError: If the URL is malformed or not allowed.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        msg = "This URL is not valid"
        raise BlockedUrlError(msg) from exc
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        msg = "Only http and https URLs are allowed"
        raise BlockedUrlError(msg)
    if parts.username is not None or parts.password is not None:
        msg = "URLs with credentials are not allowed"
        raise BlockedUrlError(msg)
    if not parts.hostname:
        msg = "This URL is not valid"
        raise BlockedUrlError(msg)
    return scheme, parts.hostname, port or (443 if scheme == "https" else 80)


def _read_limited(response: requests.Response, deadline: float) -> bytes:
    body = bytearray()
    for chunk in response.iter_content(chunk_size=_CHUNK_BYTES):
        body.extend(chunk)
        if len(body) > MAX_BYTES:
            msg = "The response is too large"
            raise FetchError(msg)
        if time.monotonic() > deadline:
            msg = "The server took too long to answer"
            raise FetchError(msg)
    return bytes(body)


def _request_address(
    url: str,
    address: str,
    headers: dict[str, str],
    deadline: float,
) -> tuple[requests.Response, bytes]:
    """Make one request to a validated address, without following redirects."""
    scheme, host, port = _checked_parts(url)
    netloc = f"[{address}]" if ":" in address else address
    parts = urlsplit(url)
    pinned_url = urlunsplit(
        (scheme, f"{netloc}:{port}", parts.path or "/", parts.query, "")
    )
    default_port = port == (443 if scheme == "https" else 80)
    host_header = host if ":" not in host else f"[{host}]"
    with requests.Session() as session:
        # Proxies from the environment would bypass the address checks.
        session.trust_env = False
        session.mount(f"{scheme}://", _PinnedAdapter(host))
        response = session.get(
            pinned_url,
            headers={
                **headers,
                "Host": host_header if default_port else f"{host_header}:{port}",
            },
            timeout=TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )
        with response:
            return response, _read_limited(response, deadline)


def _request_once(
    url: str,
    headers: dict[str, str],
    deadline: float,
) -> tuple[requests.Response, bytes]:
    """Make one request, trying each validated address until one connects.

    A dual-stack host often lists an IPv6 address first, which fails on a
    machine with no IPv6 route.
    """
    _, host, port = _checked_parts(url)
    error: requests.RequestException | None = None
    for address in resolve_host(host, port):
        if time.monotonic() > deadline:
            break
        try:
            return _request_address(url, address, headers, deadline)
        except requests.ConnectionError as exc:
            error = exc
        except requests.RequestException as exc:
            msg = "Could not reach this URL"
            raise FetchError(msg) from exc
    msg = "Could not reach this URL"
    raise FetchError(msg) from error


def fetch(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FetchResult:
    """Fetch a URL under the rules in the module docstring.

    Args:
        url: The URL.
        etag: Validator for a conditional GET.
        last_modified: Validator for a conditional GET.

    Returns:
        The final response, whatever its status.

    Raises:
        BlockedUrlError: If a URL on the way is not allowed.
        FetchError: On network errors, too many redirects, or limits reached.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    deadline = time.monotonic() + TIMEOUT_SECONDS
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        response, body = _request_once(current, headers, deadline)
        location = response.headers.get("Location")
        if response.status_code not in _REDIRECT_CODES or not location:
            return FetchResult(
                url=current,
                status=response.status_code,
                content=body,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
        current = urljoin(current, location)
    msg = "Too many redirects"
    raise FetchError(msg)
