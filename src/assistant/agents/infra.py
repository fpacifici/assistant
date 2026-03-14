import os

import dotenv


def init_environment() -> None:
    """Initialize the keys for the agents."""
    dotenv.load_dotenv()

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
    os.environ["LANGSMITH_PROJECT"] = "Assistant"
