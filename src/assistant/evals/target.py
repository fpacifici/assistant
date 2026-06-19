import json
import uuid
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT

from assistant.agents.rag import SearchAgent

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage


def _extract_source_fields(content: str | Sequence[Any]) -> tuple[list[str], list[str]]:
    """Extract `external_id` and `notebook` values from retrieved sources.

    Supports:
    - Legacy string tool payload containing lines like `Source: {...}`.
    - Dict-based payload from `retrieve_documents()`, where `content` is a list of items
      containing a `source` mapping with `external_id` and `notebook` keys.

    Args:
        content: Tool message content.

    Returns:
        A tuple ``(external_ids, notebooks)`` with first-seen order.
    """

    external_ids: list[str] = []
    notebooks: list[str] = []
    seen_external_ids: set[str] = set()
    seen_notebooks: set[str] = set()

    parsed_sources: list[Mapping[str, object]] = []

    parsed_sources = json.loads(str(content))
    for parsed in parsed_sources:
        source = parsed["source"]
        if not isinstance(source, Mapping):
            continue
        external_id = source.get("external_id")
        notebook = source.get("notebook")

        if isinstance(external_id, str) and external_id not in seen_external_ids:
            seen_external_ids.add(external_id)
            external_ids.append(external_id)
        if isinstance(notebook, str) and notebook not in seen_notebooks:
            seen_notebooks.add(notebook)
            notebooks.append(notebook)

    return external_ids, notebooks


def target(inputs: dict[str, object]) -> dict[str, object]:
    """LangSmith/OpenEvals target function.

    Args:
        inputs: Inputs dictionary provided by the evaluation harness. Expected to include
            `question` (list-like) and uses the first element as the query string.

    Returns:
        A dict with the assistant `answer` plus extracted `notes_ids` and `notebooks`.
    """

    store = SearchAgent()
    response: BaseMessage | None = None
    note_ids: list[str] = []
    notebooks: list[str] = []
    topics: list[str] = []
    thread_id = f"eval_{uuid.uuid4()}"

    question: str = str(inputs.get("question"))

    for event in store.query(thread_id, question):
        if event.type == "tool":
            content = event.content
            if isinstance(content, str | Sequence):
                extracted_note_ids, extracted_notebooks = _extract_source_fields(content)
                note_ids.extend(extracted_note_ids)
                notebooks.extend(extracted_notebooks)

        elif event.type == "ai":
            response = event

    answer: str = ""
    if response is not None:
        content = response.content
        answer = content.strip() if isinstance(content, str) else str(content).strip()

    ret: dict[str, object] = {
        "answer": answer,
        "notes_ids": note_ids,
        "topics": topics,
        "notebooks": notebooks,
    }
    return ret


def correctness_evaluator(
    inputs: dict[str, object],
    outputs: dict[str, object],
    reference_outputs: dict[str, object],
) -> object:
    """Evaluate correctness using OpenEvals judge."""

    evaluator = create_llm_as_judge(
        prompt=CORRECTNESS_PROMPT,
        model="openai:o3-mini",
        feedback_key="correctness",
    )
    return evaluator(
        inputs=inputs,
        outputs=outputs,
        reference_outputs=reference_outputs,
    )
