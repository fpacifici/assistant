"""What a link is and what it says: its type, its own title, and its text.

Everything is downloaded through the safe fetcher and only parsed as data.
The type is decided before any fetch for YouTube (by host), and from the
response's `Content-Type` otherwise. Only web pages, text files and PDFs
yield text to summarize; YouTube and other types are categorized from their
title and URL.

A site that refuses the request (a 4xx other than a timeout or rate limit,
like the 403 of a bot challenge) will refuse it again, so the link is not
retried: it is categorized from its URL alone, as a web page, or a PDF when
the path says so.

PDFs are read page by page, in order, only until there is enough text for the
model: the rest of the document is never parsed. A body larger than
`MAX_LINK_BYTES` fails at the fetcher.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from pypdf import PasswordType, PdfReader
from pypdf.errors import PyPdfError

from assistant.models.schema import ReadingLinkType
from assistant.web.fetch import FetchError, FetchResult, fetch
from assistant.web.pages import extract_page
from assistant.web.rejection import describe_rejection, summarize_rejection

logger = logging.getLogger(__name__)

# Enough for a long PDF. Web pages get the same limit: their type is only
# known once the response arrives.
MAX_LINK_BYTES = 25 * 1024 * 1024
# A 25 MB download needs more than the fetcher's default 10 s.
FETCH_TIMEOUT_SECONDS = 30
# The model reads at most this much; a PDF stops being read past it.
MAX_TEXT_CHARS = 20_000

YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
YOUTUBE_OEMBED = "https://www.youtube.com/oembed?url={url}&format=json"

_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_TEXT_TYPES = frozenset({"text/plain", "text/markdown", "text/x-markdown"})
_PDF_TYPE = "application/pdf"
# Servers often send PDFs as an unnamed binary; the magic bytes say what it is.
_UNNAMED_TYPES = frozenset({None, "application/octet-stream", "binary/octet-stream"})
_PDF_MAGIC = b"%PDF-"
_MAX_TITLE_CHARS = 300
# 4xx answers worth trying again later: timeout, too early, rate limited.
_TRANSIENT_CLIENT_ERRORS = frozenset({408, 425, 429})
_HTTP_CLIENT_ERRORS = range(400, 500)

type Fetcher = Callable[..., FetchResult]


class ExtractionError(Exception):
    """The content can't be read. The message is generic, never from the content."""


@dataclass(frozen=True, slots=True)
class ExtractedLink:
    """What a link yields. Anything but the type can be missing.

    Attributes:
        link_type: What the link points at.
        title: The link's own title: a page's `og:title` or `<title>`, a
            PDF's metadata title or first line, a video's oEmbed title.
        text: The text to summarize. None for YouTube and other types.
        author: A video's channel, as context for the category.
        partial: The text is only the beginning of a longer document.
    """

    link_type: ReadingLinkType
    title: str | None = None
    text: str | None = None
    author: str | None = None
    partial: bool = False


def _clean_title(title: str | None) -> str | None:
    if not title:
        return None
    single_line = " ".join(title.split())
    return single_line[:_MAX_TITLE_CHARS] or None


def is_youtube(url: str) -> bool:
    """Whether a URL is a YouTube video, by host."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in YOUTUBE_HOSTS


def _youtube(url: str, fetcher: Fetcher) -> ExtractedLink:
    """Title and channel from YouTube's oEmbed endpoint.

    A video oEmbed can't describe (private, removed) is still a YouTube link,
    categorized from its URL alone.
    """
    try:
        result = fetcher(YOUTUBE_OEMBED.format(url=quote(url, safe="")))
        result.raise_for_status()
        data = json.loads(result.content)
    except (FetchError, ValueError):
        logger.info("No oEmbed answer for a YouTube link", exc_info=True)
        return ExtractedLink(ReadingLinkType.YOUTUBE)
    if not isinstance(data, dict):
        return ExtractedLink(ReadingLinkType.YOUTUBE)
    title = data.get("title")
    author = data.get("author_name")
    return ExtractedLink(
        ReadingLinkType.YOUTUBE,
        title=_clean_title(title if isinstance(title, str) else None),
        author=_clean_title(author if isinstance(author, str) else None),
    )


def _charset(content_type: str | None) -> str:
    for parameter in (content_type or "").split(";")[1:]:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "charset" and value.strip():
            return value.strip().strip('"')
    return "utf-8"


def _text_file(result: FetchResult) -> ExtractedLink:
    try:
        text = result.content.decode(_charset(result.content_type), errors="replace")
    except LookupError:
        text = result.content.decode("utf-8", errors="replace")
    return ExtractedLink(ReadingLinkType.TEXT, text=text.strip() or None)


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return _clean_title(line)
    return None


def _open_pdf(content: bytes) -> PdfReader:
    """Open a PDF. One encrypted only against editing opens with no password."""
    try:
        reader = PdfReader(io.BytesIO(content))
        locked = reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED
    except (PyPdfError, ValueError, TypeError, KeyError, AttributeError) as exc:
        msg = "This PDF could not be read"
        raise ExtractionError(msg) from exc
    if locked:
        msg = "This PDF is encrypted"
        raise ExtractionError(msg)
    return reader


def read_pdf(content: bytes, max_chars: int = MAX_TEXT_CHARS) -> ExtractedLink:
    """Read a PDF's title and its first pages, up to `max_chars` of text.

    Pages are read in order and reading stops once there is enough text, so
    a long document costs only its first pages.

    Raises:
        ExtractionError: If it is not a readable PDF, or is encrypted.
    """
    reader = _open_pdf(content)
    parts: list[str] = []
    length = 0
    pages_read = 0
    try:
        metadata = reader.metadata
        metadata_title = metadata.title if metadata else None
        page_count = len(reader.pages)
        for page in reader.pages:
            if length >= max_chars:
                break
            page_text = (page.extract_text() or "").strip()
            pages_read += 1
            if page_text:
                parts.append(page_text)
                length += len(page_text)
    except (PyPdfError, ValueError, TypeError, KeyError, AttributeError) as exc:
        msg = "This PDF could not be read"
        raise ExtractionError(msg) from exc
    text = "\n\n".join(parts)
    title = metadata_title if isinstance(metadata_title, str) else None
    return ExtractedLink(
        ReadingLinkType.PDF,
        title=_clean_title(title) or _first_line(text),
        text=text[:max_chars] or None,
        partial=pages_read < page_count or len(text) > max_chars,
    )


def _link_type(result: FetchResult) -> ReadingLinkType:
    media_type = result.media_type
    if media_type in _HTML_TYPES:
        return ReadingLinkType.WEB
    if media_type in _TEXT_TYPES:
        return ReadingLinkType.TEXT
    if media_type == _PDF_TYPE or (
        media_type in _UNNAMED_TYPES and result.content.startswith(_PDF_MAGIC)
    ):
        return ReadingLinkType.PDF
    return ReadingLinkType.OTHER


def _refused(status: int) -> bool:
    """Whether the site refused the request for good: asking again won't help."""
    return status in _HTTP_CLIENT_ERRORS and status not in _TRANSIENT_CLIENT_ERRORS


def _type_from_url(url: str) -> ReadingLinkType:
    """The type of a link that can't be fetched, from its path."""
    if urlsplit(url).path.lower().endswith(".pdf"):
        return ReadingLinkType.PDF
    return ReadingLinkType.WEB


def extract_link(url: str, fetcher: Fetcher = fetch) -> ExtractedLink:
    """Fetch a link and read what it is and what it says.

    A site that refuses the request yields the type guessed from the URL and
    nothing else, so the link is categorized from its URL.

    Args:
        url: The link.
        fetcher: The safe fetcher, or a fake in tests.

    Returns:
        What the link yields.

    Raises:
        FetchError: If it can't be fetched, or answers an error worth
            retrying (5xx, 408, 425, 429).
        ExtractionError: If a PDF can't be read.
    """
    if is_youtube(url):
        return _youtube(url, fetcher)
    result = fetcher(url, max_bytes=MAX_LINK_BYTES, timeout=FETCH_TIMEOUT_SECONDS)
    if not result.ok:
        # Why the site said no: bot protection, mostly. Logs only.
        details = describe_rejection(result)
        logger.warning(
            "Reading link rejected: %s (%s)",
            url,
            summarize_rejection(details),
            extra=details,
        )
    if _refused(result.status):
        return ExtractedLink(_type_from_url(url))
    result.raise_for_status()
    link_type = _link_type(result)
    if link_type is ReadingLinkType.WEB:
        page = extract_page(result.content, result.url)
        return ExtractedLink(link_type, title=_clean_title(page.title), text=page.text)
    if link_type is ReadingLinkType.TEXT:
        return _text_file(result)
    if link_type is ReadingLinkType.PDF:
        return read_pdf(result.content)
    return ExtractedLink(link_type)
