from typing import Any, NamedTuple

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter

from assistant.adapters.content import DocumentContent
from assistant.models.database import get_database_url


def embedding_content_and_metadata(
    doc_content: DocumentContent,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the content string and metadata dict passed to the vector store for embedding.

    Args:
        doc_content: Document content with optional title and metadata.
        extra_metadata: Additional keys to merge into the metadata dict (e.g. external_id,
            source_id, format, uuid). These take precedence over doc_content.metadata.

    Returns:
        A tuple (embedding_text, metadata). embedding_text is the body decoded as UTF-8,
        optionally prefixed with the document title. metadata is a flat dict suitable
        for the vector store, with string values.
    """
    body_text = doc_content.bytes.decode("utf-8")
    title = doc_content.title
    embedding_text = f"{title}\n\n{body_text}" if title else body_text
    metadata: dict[str, Any] = {}
    if doc_content.metadata:
        for k, v in doc_content.metadata.items():
            metadata[k] = str(v)
    if title:
        metadata["title"] = title
    if extra_metadata:
        for k, v in extra_metadata.items():
            metadata[k] = str(v)
    return embedding_text, metadata


class VectorResult(NamedTuple):
    """Result of a similarity search."""

    document: Document
    score: float


class VectorStore:
    """Wrapper around the PGVector-backed LangChain vector store."""

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        """Initialize the vector store with the given embedding model.

        Args:
            model: OpenAI embedding model identifier.
        """

        self.embeddings = OpenAIEmbeddings(model=model)
        self.store = PGVector(
            embeddings=self.embeddings,
            collection_name="assistant",
            connection=get_database_url(),
        )

    def delete_collection(self) -> None:
        """Delete the assistant collection and all of its embeddings."""

        self.store.delete(collection_name="assistant")

    def embed(self, content: str, metadata: dict[str, Any]) -> list[list[float]]:
        """Generate embeddings for the given content."""

        doc = Document(page_content=content, metadata=metadata)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            add_start_index=True,
        )
        all_splits = text_splitter.split_documents([doc])

        return self.embeddings.embed_documents(
            [split.page_content for split in all_splits],
        )

    def splits(self, content: str, metadata: dict[str, Any]) -> list[Document]:
        """Split content into LangChain documents with metadata preserved."""

        doc = Document(page_content=content, metadata=metadata)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            add_start_index=True,
        )
        return text_splitter.split_documents([doc])

    def add(self, content: str, metadata: dict[str, Any]) -> None:
        """Add content and metadata as documents to the vector store."""

        self.store.add_documents(documents=self.splits(content, metadata))

    def query(self, query: str) -> list[VectorResult]:
        """Run a similarity search against the stored documents."""

        results = self.store.similarity_search_with_score(query)
        return [
            VectorResult(document=doc, score=score) for doc, score in results
        ]


def embed(content: str, metadata: dict[str, Any]) -> list[list[float]]:
    """Convenience function used by CLI code to generate embeddings.

    This creates a transient :class:`VectorStore` instance and delegates to its
    :meth:`VectorStore.embed` method.
    """

    store = VectorStore()
    return store.embed(content, metadata)
