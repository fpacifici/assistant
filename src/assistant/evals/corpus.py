"""Loads the eval corpus (`data/evals/notes/`) into an eval user's notebooks.

The corpus is one directory per notebook, one markdown file per note: the
first `# heading` is the note title and the rest becomes its blocks.
Notebooks are named `Eval: <directory>` (notebook names are global). Loading
replaces the eval user's notebooks entirely, so it can be run repeatedly.

The eval user has no credential: it cannot log in, it only owns the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from markdown_it import MarkdownIt
from sqlalchemy import select

from assistant.models.schema import MarkdownBlockType, Notebook, User
from assistant.notes.service import (
    create_note,
    create_notebook,
    delete_notebook,
    replace_markdown_nodes,
)

if TYPE_CHECKING:
    from pathlib import Path

    from markdown_it.token import Token
    from sqlalchemy.orm import Session

    from assistant.models.schema import Note

NOTEBOOK_PREFIX = "Eval: "

_MARKDOWN = MarkdownIt("commonmark")
_BLOCK_TYPES = {
    "heading_open": MarkdownBlockType.HEADING,
    "paragraph_open": MarkdownBlockType.PARAGRAPH,
    "blockquote_open": MarkdownBlockType.BLOCKQUOTE,
    "fence": MarkdownBlockType.CODE_BLOCK,
    "code_block": MarkdownBlockType.CODE_BLOCK,
}
_LISTS = {"bullet_list_open", "ordered_list_open"}


@dataclass(frozen=True, slots=True)
class CorpusNote:
    """A parsed corpus file."""

    title: str
    blocks: list[tuple[str, str]]


def _source(lines: list[str], token: Token) -> str:
    assert token.map is not None
    start, end = token.map
    return "\n".join(lines[start:end]).strip()


def markdown_blocks(text: str) -> list[tuple[str, str]]:
    """Split markdown into note blocks, as `(block_type, payload)` pairs.

    Top-level paragraphs, headings, quotes and code blocks are one block
    each; every list item is its own block. Other markdown (rules, HTML) is
    dropped.
    """
    lines = text.splitlines()
    tokens = _MARKDOWN.parse(text)
    blocks: list[tuple[str, str]] = []
    for token in tokens:
        if token.map is None:
            continue
        if token.level == 0 and token.type in _BLOCK_TYPES:
            blocks.append((_BLOCK_TYPES[token.type].value, _source(lines, token)))
        elif token.level == 1 and token.type == "list_item_open":
            blocks.append((MarkdownBlockType.LIST_ITEM.value, _source(lines, token)))
    return [(block_type, payload) for block_type, payload in blocks if payload]


def parse_note(text: str, fallback_title: str) -> CorpusNote:
    """Parse a corpus file: a leading `# Title` line, then the body."""
    lines = text.lstrip().splitlines()
    if lines and lines[0].startswith("# "):
        return CorpusNote(
            title=lines[0][2:].strip(), blocks=markdown_blocks("\n".join(lines[1:]))
        )
    return CorpusNote(title=fallback_title, blocks=markdown_blocks(text))


def get_or_create_eval_user(session: Session, email: str) -> User:
    """The eval user, created (without any credential) if missing."""
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, firstname="Eval", lastname="User")
        session.add(user)
        session.flush()
    return user


def load_corpus(session: Session, root: Path, email: str) -> list[Note]:
    """Replace the eval user's notebooks with the corpus under `root`.

    Args:
        session: The caller commits.
        root: Directory with one subdirectory of `.md` files per notebook.
        email: The eval user's email.

    Returns:
        The created notes.

    Raises:
        DuplicateNotebookNameError: If another user owns a notebook with an
            `Eval: ` name of the corpus.
    """
    user = get_or_create_eval_user(session, email)
    owned = session.scalars(select(Notebook.id).where(Notebook.owner_id == user.uid))
    for notebook_id in list(owned):
        delete_notebook(session, notebook_id, user)

    notes: list[Note] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        notebook = create_notebook(session, f"{NOTEBOOK_PREFIX}{directory.name}", user)
        for path in sorted(directory.glob("*.md")):
            parsed = parse_note(path.read_text(encoding="utf-8"), path.stem)
            note = create_note(
                session, notebook_id=notebook.id, owner=user, title=parsed.title
            )
            replace_markdown_nodes(session, note.id, user, parsed.blocks)
            notes.append(note)
    return notes
