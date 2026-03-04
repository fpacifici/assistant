"""Tests for Evernote external source adapter."""

from typing import List
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

from evernote.edam.notestore.ttypes import NoteMetadata, NotesMetadataList
import pytest

from assistant.adapters.content import DocumentContent
from assistant.adapters.evernote import EvernoteSource
from evernote.edam.type.ttypes import Note, Notebook


def _make_note_store(
    *,
    get_note_side_effect: Note | None=None,
    list_notebooks_return: List[Notebook] | None = None,
    find_notes_side_effect: NotesMetadataList | None = None,
) -> MagicMock:
    """Build a mock note store with getNoteWithResultSpec, listNotebooks, findNotesMetadata."""
    store = MagicMock()
    if get_note_side_effect is not None:
        store.getNoteWithResultSpec.side_effect = [get_note_side_effect]
    if list_notebooks_return is not None:
        store.listNotebooks.return_value = list_notebooks_return
    if find_notes_side_effect is not None:
        store.findNotesMetadata.side_effect = [find_notes_side_effect, NotesMetadataList(notes=[])]
    return store


def _make_client(note_store: MagicMock) -> MagicMock:
    """Build a mock EvernoteClientSync whose get_note_store() returns the given store."""
    client = MagicMock()
    client.get_note_store.return_value = note_store
    return client


def test_fetch_one_document() -> None:
    """Test get_document returns DocumentContent when the note exists."""
    note = Note(guid="a1b2c3d4-e5f6-7890-abcd-ef1234567890", content="<en-note>Hello</en-note>")
    note.title = "My Note Title"
    note.notebookGuid = "nb-guid-1"
    notebook = Notebook(guid="nb-guid-1", name="MyNotebook")
    note_store = _make_note_store(
        get_note_side_effect=note,
        list_notebooks_return=[notebook],
    )
    client = _make_client(note_store)

    with patch("assistant.adapters.evernote.create_client", return_value=client):
        source = EvernoteSource(notebooks=["MyNotebook"])
        doc = source.get_document("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    assert isinstance(doc, DocumentContent)
    assert doc.uuid == UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    assert doc.bytes == b"<en-note>Hello</en-note>"
    assert doc.title == "My Note Title"
    assert doc.metadata == {"notebook": "MyNotebook"}
    note_store.getNoteWithResultSpec.assert_called_once()
    note_store.listNotebooks.assert_called_once()


def test_get_document_non_existing_raises() -> None:
    """Test get_document raises when the note does not exist."""
    note_store = _make_note_store(
        get_note_side_effect=Exception("Note not found"),
    )
    client = _make_client(note_store)

    with patch("assistant.adapters.evernote.create_client", return_value=client):
        source = EvernoteSource(notebooks=["MyNotebook"])
        with pytest.raises(Exception, match="Note not found"):
            source.get_document("nonexistent-guid")
    note_store.getNoteWithResultSpec.assert_called_once()


def test_list_documents_no_notebooks() -> None:
    """Test list_documents returns empty list when no notebooks are configured."""
    note_store = _make_note_store(list_notebooks_return=[])
    client = _make_client(note_store)

    with patch("assistant.adapters.evernote.create_client", return_value=client):
        source = EvernoteSource(notebooks=[])
        result = source.list_documents(since=datetime.now(timezone.utc))

    assert result == []
    note_store.listNotebooks.assert_called_once()
    note_store.findNotesMetadata.assert_not_called()


def test_evernote_list_documents_required_notebook_not_in_list() -> None:
    """Test list_documents raises when the requested notebook is not in the account."""
    notebook = Notebook(guid="nb-guid-1", name="OtherNotebook")
    note_store = _make_note_store(list_notebooks_return=[notebook])
    client = _make_client(note_store)

    with patch("assistant.adapters.evernote.create_client", return_value=client):
        source = EvernoteSource(notebooks=["MissingNotebook"])
        with pytest.raises(ValueError, match="Notebook MissingNotebook not found"):
            source.list_documents(since=datetime.now(timezone.utc))

    note_store.listNotebooks.assert_called_once()
    note_store.findNotesMetadata.assert_not_called()


def test_evernote_list_documents() -> None:
    notebook = MagicMock()
    notebook = Notebook(guid="nb-guid-1", name="MyNotebook")
    
    notemeta1 = NoteMetadata(guid="note-guid-1")
    notemeta2 = NoteMetadata(guid="note-guid-2")
    note_store = _make_note_store(
        list_notebooks_return=[notebook], 
        find_notes_side_effect=NotesMetadataList(notes=[notemeta1, notemeta2])
    )
    client = _make_client(note_store)

    with patch("assistant.adapters.evernote.create_client", return_value=client):
        source = EvernoteSource(notebooks=["MyNotebook"])
        docs = source.list_documents(since=datetime.now(timezone.utc))

    assert docs == [notemeta1.guid, notemeta2.guid]
    note_store.listNotebooks.assert_called_once()
    

    