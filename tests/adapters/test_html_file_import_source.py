"""Tests for HTMLFileImportSource: directory traversal + per-file parsing.

Pure filesystem + parser seam, isolated from the DB pipeline.
"""

from __future__ import annotations

from pathlib import Path

from assistant.adapters.html_parser import parse_html_note
from assistant.adapters.plugins.html_file import HTMLFileImportSource

# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------


def test_list_documents_returns_one_entry_per_html_file_per_notebook(
    tmp_path: Path,
) -> None:
    work = tmp_path / "Work"
    work.mkdir()
    (work / "note1.html").write_text("<h1>Note 1</h1>")
    (work / "note2.html").write_text("<h1>Note 2</h1>")
    personal = tmp_path / "Personal"
    personal.mkdir()
    (personal / "note3.html").write_text("<h1>Note 3</h1>")

    source = HTMLFileImportSource(tmp_path)
    documents = source.list_documents()

    assert documents == sorted(documents)
    assert set(documents) == {
        "Personal/note3.html",
        "Work/note1.html",
        "Work/note2.html",
    }


def test_list_documents_ignores_non_html_files(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    work.mkdir()
    (work / "note1.html").write_text("<h1>Note 1</h1>")
    (work / "readme.txt").write_text("not html")

    source = HTMLFileImportSource(tmp_path)
    assert source.list_documents() == ["Work/note1.html"]


def test_list_documents_ignores_files_nested_more_than_one_level_deep(
    tmp_path: Path,
) -> None:
    work = tmp_path / "Work"
    work.mkdir()
    (work / "note1.html").write_text("<h1>Note 1</h1>")
    nested = work / "subdir"
    nested.mkdir()
    (nested / "deep.html").write_text("<h1>Deep note</h1>")

    source = HTMLFileImportSource(tmp_path)
    assert source.list_documents() == ["Work/note1.html"]


def test_list_documents_ignores_files_directly_in_root(tmp_path: Path) -> None:
    (tmp_path / "stray.html").write_text("<h1>Stray</h1>")
    work = tmp_path / "Work"
    work.mkdir()
    (work / "note1.html").write_text("<h1>Note 1</h1>")

    source = HTMLFileImportSource(tmp_path)
    assert source.list_documents() == ["Work/note1.html"]


# ---------------------------------------------------------------------------
# get_note
# ---------------------------------------------------------------------------


def test_get_note_returns_notebook_name_from_parent_directory(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    work.mkdir()
    (work / "note1.html").write_text("<h1>Note 1</h1>")

    source = HTMLFileImportSource(tmp_path)
    imported = source.get_note("Work/note1.html")

    assert imported.notebook_name == "Work"


def test_get_note_is_a_thin_wrapper_around_parse_html_note(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    work.mkdir()
    html = "<h1>Note 1</h1><p>Body</p>"
    (work / "note1.html").write_text(html)

    source = HTMLFileImportSource(tmp_path)
    imported = source.get_note("Work/note1.html")

    expected = parse_html_note(html, fallback_title="note1")
    assert imported.parsed == expected


def test_get_note_uses_file_stem_as_fallback_title(tmp_path: Path) -> None:
    work = tmp_path / "Work"
    work.mkdir()
    (work / "no-heading-here.html").write_text("<p>Just a paragraph</p>")

    source = HTMLFileImportSource(tmp_path)
    imported = source.get_note("Work/no-heading-here.html")

    assert imported.parsed.title == "no-heading-here"
