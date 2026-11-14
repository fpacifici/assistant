"""Test doubles for the blogs package."""

from __future__ import annotations

from dataclasses import dataclass, field

from assistant.blogs.analysis import PostAnalysis, PostToAnalyze
from assistant.web.fetch import FetchResult


@dataclass
class FakeWeb:
    """A `fetch` answering from a dict of URL to body, status or exception.

    Any other URL is a 404. `requests` records every call as (url, etag).
    """

    pages: dict[str, bytes | int | Exception] = field(default_factory=dict)
    etags: dict[str, str] = field(default_factory=dict)
    requested: list[str] = field(default_factory=list)
    conditional: list[str | None] = field(default_factory=list)

    def __call__(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,  # noqa: ARG002
    ) -> FetchResult:
        self.requested.append(url)
        self.conditional.append(etag)
        page = self.pages.get(url)
        if page is None:
            return FetchResult(url=url, status=404, content=b"")
        if isinstance(page, Exception):
            raise page
        if isinstance(page, int):
            return FetchResult(url=url, status=page, content=b"")
        return FetchResult(url=url, status=200, content=page, etag=self.etags.get(url))


@dataclass
class FakeAnalyzer:
    """A `PostAnalyzer` that records its inputs and can fail."""

    result: PostAnalysis = field(
        default_factory=lambda: PostAnalysis(
            title=None, summary="A summary.", match_level=None, motivation=None
        ),
    )
    error: Exception | None = None
    calls: list[PostToAnalyze] = field(default_factory=list)

    def analyze(self, post: PostToAnalyze) -> PostAnalysis:
        self.calls.append(post)
        if self.error is not None:
            raise self.error
        return self.result
