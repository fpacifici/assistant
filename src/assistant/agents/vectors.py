from typing import Any
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings


def embed(content: str, metadata: dict[str, Any]) -> list[list[float]]:    
    doc = Document(page_content=content, metadata=metadata)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=200, add_start_index=True
    )
    all_splits = text_splitter.split_documents([doc])

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    return embeddings.embed_documents([split.page_content for split in all_splits])