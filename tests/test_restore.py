"""Tests for restore helpers."""

from datetime import UTC, datetime

from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from assistant.models.schema import DocumentFormat, DocumentMetadata, ExternalSource
from assistant.restore import ImportedData, _restore_application_data


def test_restore_application_data_restores_document_metadata() -> None:
    """_restore_application_data should create proper ORM objects from import data."""

    source_id = "11111111-1111-1111-1111-111111111111"
    document_uuid = "22222222-2222-2222-2222-222222222222"

    data: ImportedData = {
        "external_sources": [
            {
                "id": source_id,
                "provider": "test",
                "provider_query": "{}",
            },
        ],
        "documents": [
            {
                "uuid": document_uuid,
                "external_id": "ext-1",
                "creation_datetime": datetime.now(UTC).isoformat(),
                "last_update_datetime": datetime.now(UTC).isoformat(),
                "title": "Title",
                "format": DocumentFormat.TEXT.value,
                "source_id": source_id,
            },
        ],
        "document_metadata": [
            {
                "document_uuid": document_uuid,
                "key": "notebook",
                "value": "Notebook A",
            },
        ],
        "collections": [],
        "embeddings": [],
    }

    mock_session = MagicMock(spec=Session)

    _restore_application_data(mock_session, data)

    # Ensure that one ExternalSource, one Document and one DocumentMetadata have been added.
    added_objects = [call.args[0] for call in mock_session.add.call_args_list]
    sources = [obj for obj in added_objects if isinstance(obj, ExternalSource)]
    documents = [obj for obj in added_objects if hasattr(obj, "external_id")]
    metadata_rows = [obj for obj in added_objects if isinstance(obj, DocumentMetadata)]

    assert len(sources) == 1
    assert len(documents) == 1
    assert len(metadata_rows) == 1
    meta = metadata_rows[0]
    assert meta.key == "notebook"
    assert meta.value == "Notebook A"

