"""Tests for generate_embeddings CLI script."""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from assistant.adapters.content import DocumentContent
from assistant.cli.generate_embeddings import main
from assistant.models.schema import Document, DocumentFormat


def test_generate_embeddings_success() -> None:
    """Test embedding generation: embed called with content and UUID in metadata."""
    document_uuid = uuid.uuid4()
    mock_document = MagicMock(spec=Document)
    mock_document.uuid = document_uuid
    mock_document.format = DocumentFormat.TEXT
    mock_document.title = "Test Title"
    mock_document.metadata_entries = []
    mock_document.metadata_dict = {}

    mock_session = MagicMock()
    mock_session.get.return_value = mock_document

    mock_factory = MagicMock()
    mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_factory.return_value.__exit__ = MagicMock(return_value=False)

    content_bytes = b"Hello world content"
    doc_content = DocumentContent(uuid=document_uuid, bytes=content_bytes)
    storage_path = Path("/tmp/documents")

    with (
        patch("assistant.cli.generate_embeddings.init_environment"),
        patch("assistant.cli.generate_embeddings.Config") as mock_config_cls,
        patch(
            "assistant.cli.generate_embeddings.get_session_factory",
            return_value=mock_factory,
        ),
        patch("assistant.cli.generate_embeddings.read_content", return_value=doc_content),
        patch("assistant.cli.generate_embeddings.VectorStore") as mock_store_cls,
        patch("sys.argv", ["generate_embeddings", str(document_uuid)]),
    ):
        mock_config = MagicMock()
        mock_config.get_document_storage_path.return_value = storage_path
        mock_config_cls.return_value = mock_config

        mock_store = MagicMock()
        mock_store.embed.return_value = [[0.1] * 1536]
        mock_store_cls.return_value = mock_store

        result = main()

    assert result == 0
    mock_session.get.assert_called_once_with(Document, document_uuid)
    mock_store.embed.assert_called_once_with(
        "Test Title\n\nHello world content",
        {"uuid": str(document_uuid), "title": "Test Title"},
    )


def test_generate_embeddings_document_not_found() -> None:
    """Test that missing document returns 1."""
    document_uuid = uuid.uuid4()
    mock_session = MagicMock()
    mock_session.get.return_value = None

    mock_factory = MagicMock()
    mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_factory.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("assistant.cli.generate_embeddings.init_environment"),
        patch("assistant.cli.generate_embeddings.Config") as mock_config_cls,
        patch(
            "assistant.cli.generate_embeddings.get_session_factory",
            return_value=mock_factory,
        ),
        patch("sys.argv", ["generate_embeddings", str(document_uuid)]),
    ):
        mock_config = MagicMock()
        mock_config.get_document_storage_path.return_value = Path("/tmp/documents")
        mock_config_cls.return_value = mock_config

        result = main()

    assert result == 1
    mock_session.get.assert_called_once_with(Document, document_uuid)


def test_generate_embeddings_content_not_found() -> None:
    """Test that missing content returns 1."""
    document_uuid = uuid.uuid4()
    mock_document = MagicMock(spec=Document)
    mock_document.uuid = document_uuid
    mock_document.format = DocumentFormat.MARKDOWN

    mock_session = MagicMock()
    mock_session.get.return_value = mock_document

    mock_factory = MagicMock()
    mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_factory.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("assistant.cli.generate_embeddings.init_environment"),
        patch("assistant.cli.generate_embeddings.Config") as mock_config_cls,
        patch(
            "assistant.cli.generate_embeddings.get_session_factory",
            return_value=mock_factory,
        ),
        patch("assistant.cli.generate_embeddings.read_content", return_value=None),
        patch("sys.argv", ["generate_embeddings", str(document_uuid)]),
    ):
        mock_config = MagicMock()
        mock_config.get_document_storage_path.return_value = Path("/tmp/documents")
        mock_config_cls.return_value = mock_config

        result = main()

    assert result == 1


def test_generate_embeddings_pdf_unsupported() -> None:
    """Test that PDF format returns 1."""
    document_uuid = uuid.uuid4()
    mock_document = MagicMock(spec=Document)
    mock_document.uuid = document_uuid
    mock_document.format = DocumentFormat.PDF

    mock_session = MagicMock()
    mock_session.get.return_value = mock_document

    mock_factory = MagicMock()
    mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_factory.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("assistant.cli.generate_embeddings.init_environment"),
        patch("assistant.cli.generate_embeddings.Config") as mock_config_cls,
        patch(
            "assistant.cli.generate_embeddings.get_session_factory",
            return_value=mock_factory,
        ),
        patch("sys.argv", ["generate_embeddings", str(document_uuid)]),
    ):
        mock_config = MagicMock()
        mock_config.get_document_storage_path.return_value = Path("/tmp/documents")
        mock_config_cls.return_value = mock_config

        result = main()

    assert result == 1
    mock_session.get.assert_called_once_with(Document, document_uuid)
