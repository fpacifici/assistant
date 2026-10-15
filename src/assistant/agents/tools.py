"""The Ask AI agent's tools, each running with the asking user's permissions.

Tools are built per question for one user (`build_tools`). Each call opens
its own short database session, so a tool always sees the current
entitlements: a note shared or unshared mid-conversation is found or hidden
on the next call.

Every tool returns `(content, artifact)`: `content` is the text the model
reads, `artifact` the list of `Source`s it drew on, which the API streams
to the UI as links and which the checkpointer keeps with the conversation.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, TypedDict

from langchain.tools import tool
from sqlalchemy import select

from assistant.models.schema import Node, PermissionName, User
from assistant.notes.exceptions import NoteNotFoundError
from assistant.notes.permissions import require_note_access
from assistant.search.query import EmptySearchQueryError
from assistant.search.service import search
from assistant.vectors.markdown import note_markdown

if TYPE_CHECKING:
    from collections.abc import Iterable

    from langchain_core.tools import BaseTool
    from sqlalchemy.orm import Session, sessionmaker

    from assistant.models.schema import Note
    from assistant.vectors.search import NoteSearcher

# Longest note body returned by `get_note`, in characters.
MAX_NOTE_CHARS = 20_000
KEYWORD_SEARCH_LIMIT = 10


class Source(TypedDict):
    """A note an answer drew on, as shown to the user."""

    note_id: str
    notebook_id: str
    title: str
    notebook_name: str


def unique_sources(sources: Iterable[Source]) -> list[Source]:
    """Drop repeated notes, keeping the first occurrence of each."""
    seen: set[str] = set()
    result: list[Source] = []
    for source in sources:
        if source["note_id"] not in seen:
            seen.add(source["note_id"])
            result.append(source)
    return result


def _note_source(note: Note) -> Source:
    return {
        "note_id": str(note.id),
        "notebook_id": str(note.notebook_id),
        "title": note.title,
        "notebook_name": note.notebook.name,
    }


def build_tools(
    session_factory: sessionmaker[Session],
    user_id: uuid.UUID,
    searcher: NoteSearcher,
) -> list[BaseTool]:
    """The agent's tools, bound to one user.

    Args:
        session_factory: Each tool call opens and closes its own session.
        user_id: The user asking; tools only see what they can view.
        searcher: Semantic search over note chunks.
    """

    @tool(response_format="content_and_artifact")
    def search_notes(query: str) -> tuple[str, list[Source]]:
        """Semantic search over the user's notes.

        Returns the passages closest in meaning to `query`, each preceded by
        the id, title and notebook of its note. Use it first for any
        question about the user's notes; rephrase and search again if the
        passages don't answer the question.
        """
        with session_factory() as session:
            user = session.get(User, user_id)
            hits = searcher.search(session, user, query) if user is not None else []
        if not hits:
            return "No matching notes.", []
        content = "\n\n---\n\n".join(
            f"note_id: {hit.note_id}\n{hit.content}" for hit in hits
        )
        sources = unique_sources(
            {
                "note_id": str(hit.note_id),
                "notebook_id": str(hit.notebook_id),
                "title": hit.title,
                "notebook_name": hit.notebook_name,
            }
            for hit in hits
        )
        return content, sources

    @tool(response_format="content_and_artifact")
    def get_note(note_id: str) -> tuple[str, list[Source]]:
        """Read a whole note, as markdown, by its note_id.

        Use it when a passage found by search_notes or keyword_search looks
        relevant but is cut short, or to answer from the full note.
        """
        try:
            parsed_id = uuid.UUID(note_id.strip())
        except ValueError:
            return f"Invalid note_id: {note_id!r}", []
        with session_factory() as session:
            user = session.get(User, user_id)
            if user is None:
                return "Note not found.", []
            try:
                note = require_note_access(
                    session, parsed_id, user, PermissionName.VIEW_NOTE
                )
            except NoteNotFoundError:
                return "Note not found.", []
            nodes = session.scalars(
                select(Node).where(Node.note_id == note.id).order_by(Node.position),
            )
            body = note_markdown(nodes)
            if len(body) > MAX_NOTE_CHARS:
                body = body[:MAX_NOTE_CHARS] + "\n\n[note truncated]"
            content = (
                f"Title: {note.title}\n"
                f"Notebook: {note.notebook.name}\n"
                f"Created: {note.creation_timestamp.date().isoformat()}\n"
                f"Updated: {note.update_timestamp.date().isoformat()}\n\n"
                f"{body}"
            )
            return content, [_note_source(note)]

    @tool(response_format="content_and_artifact")
    def keyword_search(query: str) -> tuple[str, list[Source]]:
        """Exact keyword search over the user's notes (titles and text).

        All words must appear in a note. Use it for names, codes, rare words
        or exact phrases (in double quotes) that semantic search may miss.
        `tag:name` restricts to notes with that tag. Returns matching note
        ids, titles and snippets.
        """
        with session_factory() as session:
            user = session.get(User, user_id)
            if user is None:
                return "No matching notes.", []
            try:
                results = search(session, user, query, limit=KEYWORD_SEARCH_LIMIT)
            except EmptySearchQueryError:
                return "The query has no words to search for.", []
            if not results.hits:
                return "No matching notes.", []
            lines: list[str] = []
            for hit in results.hits:
                snippets = " … ".join(
                    "".join(segment.text for segment in snippet.segments)
                    for snippet in hit.snippets
                )
                lines.append(
                    f"note_id: {hit.note.id}\nTitle: {hit.note.title}\n"
                    f"Notebook: {hit.note.notebook.name}\nSnippets: {snippets}",
                )
            sources = [_note_source(hit.note) for hit in results.hits]
        return "\n\n---\n\n".join(lines), sources

    return [search_notes, get_note, keyword_search]
