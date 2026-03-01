from typing import Any, List, NamedTuple, Tuple
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from assistant.models.database import get_database_url

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

