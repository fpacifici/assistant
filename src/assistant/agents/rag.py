from typing import Generator, List, Tuple
from langchain.tools import tool
from langchain_core.documents import Document

from assistant.agents.vectors import VectorResult, VectorStore
from langchain.agents import create_agent

@tool(response_format="content_and_artifact")
def retrieve_documents(query: str) -> Tuple[str, List[Document]]:
    """Retrieve documents from the vector store."""
    
    vector_store = VectorStore()
    retrieved_docs = vector_store.query(query)
    serialized = "\n\n".join(
        (f"Source: {doc.document.metadata}\nContent: {doc.document.page_content}")
        for doc in retrieved_docs
    )
    docs = [doc.document for doc in retrieved_docs]
    return serialized, docs


class SearchAgent:

    def __init__(self) -> None:
        tools = [retrieve_documents]
        
        prompt = (
            "You are a knowledgeable assistant who can provide a summary about a "
            "topic described on a list of documents. "
            "You are given access to a tool to retrieve the documents. "
            "Use the tool to perform queries on the documents to answer the user's question."
        )
        self.agent = create_agent("gpt-4.1", tools, system_prompt=prompt)

    def query(self, query: str) -> Generator[str, None, None]:
        for event in self.agent.stream(
            {"messages": [{"role": "user", "content": query}]},
            stream_mode="values",
        ):
            yield event["messages"][-1]
