from typing import Generator, List, Optional, Tuple

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

from assistant.agents.vectors import VectorResult, VectorStore
from langgraph.checkpoint.postgres import PostgresSaver

from assistant.models.database import get_database_url  
from langchain_core.runnables import RunnableConfig


@tool(response_format="content_and_artifact")
def retrieve_documents(query: str) -> Tuple[str, List[Document]]:
    """Retrieve documents from the vector store."""
    
    retrieved_docs = VectorStore().query(query)
    serialized = "\n\n".join(
        (f"Source: {doc.document.metadata}\nContent: {doc.document.page_content}")
        for doc in retrieved_docs
    )
    docs = [doc.document for doc in retrieved_docs]
    return serialized, docs


class SearchAgent:

    def __init__(self) -> None:
        self.tools = [retrieve_documents]
        self.prompt = (
            "You are a knowledgeable assistant who can provide a summary about a "
            "topic described on a list of documents. "
            "You are given access to a tool to retrieve the documents. "
            "Use the tool to perform queries on the documents to answer the user's question."
        )
        
        

    def query(self, thread_id: str, query: str) -> Generator[BaseMessage, None, None]:
        config = RunnableConfig({"configurable": {"thread_id": thread_id}})
        with PostgresSaver.from_conn_string(get_database_url()) as checkpointer:
            self.agent = create_agent("gpt-4.1", self.tools, system_prompt=self.prompt, checkpointer=checkpointer)
            for event in self.agent.stream(
                {"messages": [{"role": "user", "content": query}]},
                stream_mode="values", 
                config=config,
            ):
                yield event["messages"][-1]
