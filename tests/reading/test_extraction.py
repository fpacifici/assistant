"""Tests for reading what a link is. Nothing here touches the network."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from assistant.fetch import FetchError, FetchResult
from assistant.models.schema import ReadingLinkType
from assistant.reading.extraction import (
    FETCH_TIMEOUT_SECONDS,
    MAX_LINK_BYTES,
    ExtractionError,
    extract_link,
    is_youtube,
    read_pdf,
)

ARTICLE = "https://example.com/article"


@dataclass
class FakeFetcher:
    """Answers from a dict of URL to (content type, body), status or exception."""

    pages: dict[str, tuple[str | None, bytes] | int | Exception] = field(
        default_factory=dict
    )
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def __call__(self, url: str, **kwargs: object) -> FetchResult:
        self.calls.append((url, kwargs))
        page = self.pages.get(url, 404)
        if isinstance(page, Exception):
            raise page
        if isinstance(page, int):
            return FetchResult(url=url, status=page, content=b"")
        content_type, body = page
        return FetchResult(url=url, status=200, content=body, content_type=content_type)


def _pdf(pages: list[str], title: str | None = None) -> bytes:
    """A PDF with one line of text per page."""
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for text in pages:
        page = writer.add_blank_page(612, 792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if title:
        writer.add_metadata({"/Title": title})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# --- YouTube ---


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://youtube.com/watch?v=abc",
        "https://m.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "https://WWW.YOUTUBE.COM/watch?v=abc",
    ],
)
def test_youtube_hosts(url: str) -> None:
    assert is_youtube(url)


def test_other_hosts_are_not_youtube() -> None:
    assert not is_youtube("https://notyoutube.com/watch?v=abc")
    assert not is_youtube("https://youtube.com.evil.example/watch")


def test_youtube_reads_oembed_and_never_fetches_the_page() -> None:
    url = "https://www.youtube.com/watch?v=abc"
    oembed = (
        "https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch"
        "%3Fv%3Dabc&format=json"
    )
    body = json.dumps({"title": "A talk", "author_name": "A channel"}).encode()
    fetcher = FakeFetcher({oembed: ("application/json", body)})
    extracted = extract_link(url, fetcher)
    assert extracted.link_type is ReadingLinkType.YOUTUBE
    assert (extracted.title, extracted.author, extracted.text) == (
        "A talk",
        "A channel",
        None,
    )
    assert [call[0] for call in fetcher.calls] == [oembed]


@pytest.mark.parametrize("answer", [404, FetchError("down"), ("text/html", b"not json")])
def test_youtube_without_oembed_is_still_youtube(
    answer: tuple[str, bytes] | int | Exception,
) -> None:
    oembed = "https://www.youtube.com/oembed?url=https%3A%2F%2Fyoutu.be%2Fx&format=json"
    fetcher = FakeFetcher({oembed: answer})
    extracted = extract_link("https://youtu.be/x", fetcher)
    assert extracted.link_type is ReadingLinkType.YOUTUBE
    assert extracted.title is None


# --- Fetching ---


def test_links_are_fetched_with_the_pdf_limits() -> None:
    fetcher = FakeFetcher({ARTICLE: ("image/png", b"\x89PNG")})
    extract_link(ARTICLE, fetcher)
    assert fetcher.calls[0][1] == {
        "max_bytes": MAX_LINK_BYTES,
        "timeout": FETCH_TIMEOUT_SECONDS,
    }


def test_http_error_raises() -> None:
    with pytest.raises(FetchError, match="HTTP 404"):
        extract_link(ARTICLE, FakeFetcher())


# --- Web pages and text ---


def test_web_page_text_and_title() -> None:
    paragraph = "Databases store data in pages on disk. " * 20
    html = (
        "<html><head><title>Plain</title>"
        '<meta property="og:title" content="The real title"></head>'
        f"<body><article><h1>Heading</h1><p>{paragraph}</p></article></body></html>"
    )
    fetcher = FakeFetcher({ARTICLE: ("text/html; charset=utf-8", html.encode())})
    extracted = extract_link(ARTICLE, fetcher)
    assert extracted.link_type is ReadingLinkType.WEB
    assert extracted.title == "The real title"
    assert extracted.text is not None
    assert "Databases store data" in extracted.text


@pytest.mark.parametrize("content_type", ["text/plain", "text/markdown; charset=latin-1"])
def test_text_files_are_used_as_they_are(content_type: str) -> None:
    fetcher = FakeFetcher({ARTICLE: (content_type, "# Notes\n\ncafé".encode("latin-1"))})
    extracted = extract_link(ARTICLE, fetcher)
    assert extracted.link_type is ReadingLinkType.TEXT
    assert extracted.text is not None
    assert extracted.text.startswith("# Notes")
    assert extracted.title is None


@pytest.mark.parametrize(
    "content_type", ["image/png", "application/zip", "video/mp4", None]
)
def test_other_types_have_no_text(content_type: str | None) -> None:
    fetcher = FakeFetcher({ARTICLE: (content_type, b"\x00\x01binary")})
    extracted = extract_link(ARTICLE, fetcher)
    assert extracted.link_type is ReadingLinkType.OTHER
    assert extracted.text is None


# --- PDFs ---


def test_pdf_title_from_metadata() -> None:
    body = _pdf(["Abstract: we study B-trees."], title="On B-trees")
    extracted = extract_link(ARTICLE, FakeFetcher({ARTICLE: ("application/pdf", body)}))
    assert extracted.link_type is ReadingLinkType.PDF
    assert extracted.title == "On B-trees"
    assert extracted.text == "Abstract: we study B-trees."
    assert not extracted.partial


def test_pdf_title_falls_back_to_the_first_line() -> None:
    extracted = read_pdf(_pdf(["First line here", "Second page"]))
    assert extracted.title == "First line here"
    assert extracted.text == "First line here\n\nSecond page"


def test_pdf_sent_as_a_binary_is_recognized() -> None:
    fetcher = FakeFetcher({ARTICLE: ("application/octet-stream", _pdf(["Hello"]))})
    assert extract_link(ARTICLE, fetcher).link_type is ReadingLinkType.PDF


def test_pdf_stops_reading_at_the_limit() -> None:
    extracted = read_pdf(_pdf(["a" * 30, "b" * 30, "c" * 30, "d" * 30]), max_chars=50)
    assert extracted.partial
    assert extracted.text is not None
    assert len(extracted.text) == 50
    assert "c" not in extracted.text


def test_broken_pdf_is_an_extraction_error() -> None:
    fetcher = FakeFetcher({ARTICLE: ("application/pdf", b"%PDF-1.4 garbage")})
    with pytest.raises(ExtractionError, match="could not be read"):
        extract_link(ARTICLE, fetcher)


def test_encrypted_pdf_is_an_extraction_error() -> None:
    writer = PdfWriter()
    writer.add_blank_page(612, 792)
    writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ExtractionError, match="encrypted"):
        read_pdf(out.getvalue())


def test_pdf_locked_only_against_editing_is_read() -> None:
    reader_input = io.BytesIO(_pdf(["Readable text"]))
    writer = PdfWriter(clone_from=reader_input)
    writer.encrypt(user_password="", owner_password="owner")
    out = io.BytesIO()
    writer.write(out)
    assert read_pdf(out.getvalue()).text == "Readable text"
