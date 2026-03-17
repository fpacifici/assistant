from collections.abc import Generator
from typing import cast

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver

from assistant.agents.vectors import VectorStore
from assistant.models.database import get_database_url


@tool(response_format="content_and_artifact")
def retrieve_documents(query: str) -> tuple[str, list[Document]]:
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
            "Use the tool to query the documents to answer the user's question."
        )

    def query(self, thread_id: str, query: str) -> Generator[BaseMessage]:
        config = RunnableConfig({"configurable": {"thread_id": thread_id}})
        with PostgresSaver.from_conn_string(get_database_url()) as checkpointer:
            self.agent = create_agent(
                "gpt-4.1",
                self.tools,
                system_prompt=self.prompt,
                checkpointer=checkpointer,
            )
            for event in self.agent.stream(
                {"messages": [{"role": "user", "content": query}]},
                stream_mode="values",
                config=config,
            ):
                yield event["messages"][-1]

    def load(self, thread_id: str) -> Generator[BaseMessage]:
        """Load and stream the full conversation history for a given thread.

        Args:
            thread_id: Identifier of the conversation thread to load.

        Yields:
            Each message in the stored conversation history, in order.
        """
        config = RunnableConfig({"configurable": {"thread_id": thread_id}})
        with PostgresSaver.from_conn_string(get_database_url()) as checkpointer:
            checkpoint_tuple = checkpointer.get_tuple(config)
            if checkpoint_tuple is None:
                return

            checkpoint = checkpoint_tuple.checkpoint
            channel_values = checkpoint["channel_values"]
            messages = cast(list[BaseMessage], channel_values["messages"])
            yield from messages
