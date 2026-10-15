"""Tests for the eval corpus loader, and for the corpus and dataset files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from assistant.evals.corpus import (
    NOTEBOOK_PREFIX,
    load_corpus,
    markdown_blocks,
    parse_note,
)
from assistant.evals.dataset import load_examples
from assistant.models.schema import Node, Note, Notebook, User
from assistant.notes.exceptions import DuplicateNotebookNameError
from assistant.notes.service import create_notebook

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "data" / "evals" / "notes"
DATASET = REPO_ROOT / "data" / "evals" / "dataset.yaml"
EMAIL = "eval@assistant.invalid"


# --- Parsing ---


def test_markdown_blocks() -> None:
    text = (
        "## Plan\n\nFirst paragraph\nstill first.\n\n- one\n- two\n\n"
        "> quoted\n\n```\ncode\n```\n\n1. first\n"
    )

    assert markdown_blocks(text) == [
        ("heading", "## Plan"),
        ("paragraph", "First paragraph\nstill first."),
        ("list_item", "- one"),
        ("list_item", "- two"),
        ("blockquote", "> quoted"),
        ("code_block", "```\ncode\n```"),
        ("list_item", "1. first"),
    ]


def test_parse_note_takes_the_title_from_the_first_heading() -> None:
    note = parse_note("# Rome trip\n\nWe saw the Colosseum.\n", "fallback")

    assert note.title == "Rome trip"
    assert note.blocks == [("paragraph", "We saw the Colosseum.")]


def test_parse_note_without_heading_uses_the_fallback_title() -> None:
    assert parse_note("Just text.", "file-name").title == "file-name"


# --- Loading ---


def _corpus(root: Path) -> Path:
    (root / "Travel").mkdir(parents=True)
    (root / "Travel" / "rome.md").write_text("# Rome\n\n## Day 1\n\nColosseum.\n")
    (root / "Home").mkdir()
    (root / "Home" / "boiler.md").write_text("# Boiler\n\n- service in November\n")
    return root


def test_load_corpus_creates_the_user_notebooks_and_notes(
    db_session: Session,
    tmp_path: Path,
) -> None:
    notes = load_corpus(db_session, _corpus(tmp_path), EMAIL)

    user = db_session.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    notebooks = db_session.scalars(select(Notebook).where(Notebook.owner_id == user.uid))
    assert sorted(n.name for n in notebooks) == [
        f"{NOTEBOOK_PREFIX}Home",
        f"{NOTEBOOK_PREFIX}Travel",
    ]
    assert [note.title for note in notes] == ["Boiler", "Rome"]
    rome_nodes = db_session.scalars(
        select(Node).where(Node.note_id == notes[1].id).order_by(Node.position),
    )
    assert [(n.block_type, n.payload) for n in rome_nodes] == [
        ("heading", "## Day 1"),
        ("paragraph", "Colosseum."),
    ]


def test_loading_again_replaces_the_corpus(db_session: Session, tmp_path: Path) -> None:
    root = _corpus(tmp_path)
    load_corpus(db_session, root, EMAIL)

    load_corpus(db_session, root, EMAIL)

    assert db_session.query(Note).count() == 2


def test_loading_refuses_notebooks_of_other_users(
    db_session: Session,
    tmp_path: Path,
) -> None:
    someone = User(email="someone@test.com", firstname="S", lastname="O")
    db_session.add(someone)
    db_session.flush()
    create_notebook(db_session, f"{NOTEBOOK_PREFIX}Home", someone)

    with pytest.raises(DuplicateNotebookNameError):
        load_corpus(db_session, _corpus(tmp_path), EMAIL)


# --- The fixture files ---


def test_corpus_has_notebooks_of_titled_notes() -> None:
    notebooks = sorted(p for p in CORPUS.iterdir() if p.is_dir())
    assert len(notebooks) >= 3
    for path in CORPUS.glob("*/*.md"):
        note = parse_note(path.read_text(encoding="utf-8"), "")
        assert note.title, path
        assert note.blocks, path


def test_dataset_expects_notes_that_exist_in_the_corpus() -> None:
    titles = {
        parse_note(path.read_text(encoding="utf-8"), "").title
        for path in CORPUS.glob("*/*.md")
    }
    examples = load_examples(DATASET)

    assert len(examples) >= 8
    assert any(not e["outputs"]["sources"] for e in examples), "no unanswerable question"
    for example in examples:
        assert example["outputs"]["answer"], example
        assert set(example["outputs"]["sources"]) <= titles, example
