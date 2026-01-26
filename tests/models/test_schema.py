"""Tests for database models."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from assistant.models.schema import Document, DocumentFormat, ExternalSource


def test_external_source_creation(db_session: Session) -> None:
    """Test creating an ExternalSource."""
    source = ExternalSource(
        provider="fake",
        provider_query='{"notebook": "test"}',
    )
    db_session.add(source)
    db_session.commit()

    assert source.id is not None
    assert source.provider == "fake"
    assert source.provider_query == '{"notebook": "test"}'


def test_document_creation(db_session: Session) -> None:
    """Test creating a Document."""
    source = ExternalSource(provider="fake")
    db_session.add(source)
    db_session.flush()

    doc = Document(
        external_id="doc1",
        creation_datetime=datetime.now(UTC),
        last_update_datetime=datetime.now(UTC),
        title="Test Document",
        format=DocumentFormat.TEXT,
        source_id=source.id,
    )
    db_session.add(doc)
    db_session.commit()

    assert doc.uuid is not None
    assert doc.external_id == "doc1"
    assert doc.title == "Test Document"
    assert doc.format == DocumentFormat.TEXT
    assert doc.source_id == source.id


def test_document_external_source_relationship(db_session: Session) -> None:
    """Test relationship between Document and ExternalSource."""
    source = ExternalSource(provider="fake")
    db_session.add(source)
    db_session.flush()

    doc = Document(
        external_id="doc1",
        creation_datetime=datetime.now(UTC),
        last_update_datetime=datetime.now(UTC),
        title="Test Document",
        format=DocumentFormat.TEXT,
        source_id=source.id,
    )
    db_session.add(doc)
    db_session.commit()

    # Test relationship
    assert doc.source.id == source.id
    assert doc in source.documents


def test_document_format_enum(db_session: Session) -> None:
    """Test DocumentFormat enum values."""
    source = ExternalSource(provider="fake")
    db_session.add(source)
    db_session.flush()

    for format_value in DocumentFormat:
        doc = Document(
            external_id=f"doc_{format_value.value}",
            creation_datetime=datetime.now(UTC),
            last_update_datetime=datetime.now(UTC),
            title=f"Test {format_value.value}",
            format=format_value,
            source_id=source.id,
        )
        db_session.add(doc)

    db_session.commit()

    docs = db_session.query(Document).all()
    assert len(docs) == 3  # TEXT, MARKDOWN, PDF
