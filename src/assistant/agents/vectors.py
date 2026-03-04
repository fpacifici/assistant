from typing import Any, List, NamedTuple

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
    document: Document
    score: float

class VectorStore:

    def __init__(self, model: str = "text-embedding-3-small"):
        self.embeddings = OpenAIEmbeddings(model=model)
        self.store = PGVector(
            embeddings=self.embeddings,
            collection_name="assistant",
            connection=get_database_url(),
        )
    

    def delete_collection(self) -> None:
        self.store.delete(collection_name="assistant")

    def embed(self, content: str, metadata: dict[str, Any]) -> list[list[float]]:    
        doc = Document(page_content=content, metadata=metadata)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200, add_start_index=True
        )
        all_splits = text_splitter.split_documents([doc])

        return self.embeddings.embed_documents([split.page_content for split in all_splits])

    def splits(self, content: str, metadata: dict[str, Any]) -> List[Document]:
        doc = Document(page_content=content, metadata=metadata)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200, add_start_index=True
        )
        return text_splitter.split_documents([doc])


    def add(self, content: str, metadata: dict[str, Any]) -> None:
        ids = self.store.add_documents(documents=self.splits(content, metadata))
    
    def query(self, query: str) -> List[VectorResult]:
        result = self.store.similarity_search_with_score(query)
        return [VectorResult(document=result[0], score=result[1]) for result in result]

