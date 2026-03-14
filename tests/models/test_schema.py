"""Tests for ORM models and helpers."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from assistant.models.schema import (
    Document,
    DocumentFormat,
    DocumentMetadata,
    ExternalSource,
)


def test_document_set_metadata_creates_and_updates(db_session: Session) -> None:
    """Test that Document.set_metadata creates and updates metadata rows."""

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

    # Create metadata entry
    document.set_metadata("notebook", "Notebook A")
    db_session.flush()

    rows = db_session.query(DocumentMetadata).all()
    assert len(rows) == 1
    assert rows[0].document_uuid == document.uuid
    assert rows[0].key == "notebook"
    assert rows[0].value == "Notebook A"

    # Update existing key
    document.set_metadata("notebook", "Notebook B")
    db_session.flush()

    rows = db_session.query(DocumentMetadata).all()
    assert len(rows) == 1
    assert rows[0].value == "Notebook B"
    assert document.metadata_dict == {"notebook": "Notebook B"}
