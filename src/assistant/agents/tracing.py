"""LangSmith tracing for the agent and the evals.

langchain reads its tracing settings from environment variables. Tracing is
switched on only when `LANGSMITH_API_KEY` is set (in the environment or
`.env`, loaded by `assistant.config`), so a server without the key never
tries to send traces. Runs then go to the `ai.langsmith_project` project
(default "Assistant").
"""

from __future__ import annotations

import logging
import os

from assistant.config import Config

logger = logging.getLogger(__name__)

LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"


def configure_tracing(config: Config | None = None) -> bool:
    """Set the LangSmith environment variables from config.

    Args:
        config: Where to read `ai.*` from; defaults to `Config()`.

    Returns:
        Whether tracing is enabled.
    """
    ai_config = (config or Config()).get_ai_config()
    if not ai_config["langsmith_enabled"]:
        os.environ["LANGSMITH_TRACING"] = "false"
        return False
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ.setdefault("LANGSMITH_ENDPOINT", LANGSMITH_ENDPOINT)
    os.environ["LANGSMITH_PROJECT"] = ai_config["langsmith_project"]
    logger.info("LangSmith tracing enabled (project %s)", ai_config["langsmith_project"])
    return True
