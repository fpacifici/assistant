from logging import getLogger
from typing import Any, NamedTuple

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter

from assistant.models.database import get_database_url

logger = getLogger(__name__)


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
        logger.info("Initializing PGVector with collection name: assistant")
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
        return [VectorResult(document=doc, score=score) for doc, score in results]


_default_store: VectorStore | None = None


def init_vector_store(model: str = "text-embedding-3-small") -> VectorStore:
    """Return a shared VectorStore instance.

    PGVector (and thus VectorStore) must not be constructed more than once per
    process when used from tools, because langchain_postgres uses a shared
    SQLAlchemy Base; redefining the same tables raises InvalidRequestError.
    This lazy singleton ensures a single store is reused.

    Args:
        model: OpenAI embedding model identifier (used only on first call).

    Returns:
        The shared VectorStore instance.
    """
    global _default_store  # noqa: PLW0603
    if _default_store is None:
        _default_store = VectorStore(model=model)
    return _default_store
