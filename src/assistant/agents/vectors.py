from typing import Any, List, NamedTuple

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter

from assistant.models.database import get_database_url


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
        """Generate embeddings for the given content.

        Args:
            content: Text content to embed.
            metadata: Metadata to associate with the content.

        Returns:
            A list of embedding vectors (one per text chunk).
        """

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

    def splits(self, content: str, metadata: dict[str, Any]) -> List[Document]:
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

    def query(self, query: str) -> List[VectorResult]:
        """Run a similarity search against the stored documents."""

        results = self.store.similarity_search_with_score(query)
        return [
            VectorResult(document=doc, score=score) for doc, score in results
        ]


def embed(content: str, metadata: dict[str, Any]) -> list[list[float]]:
    """Convenience function used by CLI code to generate embeddings.

    This creates a transient :class:`VectorStore` instance and delegates to its
    :meth:`VectorStore.embed` method.

    Args:
        content: Text content to embed.
        metadata: Metadata to associate with the content.

    Returns:
        A list of embedding vectors (one per text chunk).
    """

    store = VectorStore()
    return store.embed(content, metadata)
