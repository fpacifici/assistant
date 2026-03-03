"""Tests for export helpers."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from assistant.export import ExportedDocumentMetadata, _export_application_data
from assistant.models.schema import Document, DocumentFormat, DocumentMetadata, ExternalSource


def test_export_application_data_includes_document_metadata(db_session: Session) -> None:
    """Exported application data should include document metadata entries."""

    source = ExternalSource(provider="test", provider_query="{}")
    db_session.add(source)
    db_session.flush()

    document = Document(
        external_id="ext-1",
        creation_datetime=datetime.now(UTC),
        last_update_datetime=datetime.now(UTC),
        title="Title",
        format=DocumentFormat.TEXT,
        source_id=source.id,
    )
    db_session.add(document)
    db_session.flush()

    metadata = DocumentMetadata(
        document_uuid=document.uuid,
        key="notebook",
        value="Notebook A",
    )
    db_session.add(metadata)
    db_session.commit()

    external_sources, documents, document_metadata = _export_application_data(db_session)

    assert len(external_sources) == 1
    assert len(documents) == 1
    assert len(document_metadata) == 1

    exported_meta: ExportedDocumentMetadata = document_metadata[0]
    assert exported_meta["document_uuid"] == str(document.uuid)
    assert exported_meta["key"] == "notebook"
    assert exported_meta["value"] == "Notebook A"

