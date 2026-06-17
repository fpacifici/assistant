"""Tests for evaluation target parsing helpers."""

from assistant.evals.target import _extract_source_fields


def test_extract_source_fields_with_multiple_source_blocks() -> None:
    """Extract external IDs and notebooks from multiple Source lines."""
    content = (
        "Source: {'title': 'A', 'notebook': 'dist/stream', 'external_id': 'id-1'}\n"
        "Content: first\n"
        "Source: {'title': 'B', 'notebook': 'dist/stream', 'external_id': 'id-2'}\n"
        "Content: second\n"
        "Source: {'title': 'C', 'notebook': 'dist/other', 'external_id': 'id-1'}\n"
        "Content: duplicate external_id, new notebook\n"
        "Source: not-a-dict\n"
        "Content: ignored\n"
    )

    external_ids, notebooks = _extract_source_fields(content)

    assert external_ids == ["id-1", "id-2"]
    assert notebooks == ["dist/stream", "dist/other"]


def test_extract_source_fields_from_dict_content_items() -> None:
    """Extract fields from dict-based tool payload with multiple sources."""
    content: list[object] = [
        {
            "source": {
                "title": "A",
                "notebook": "dist/stream",
                "external_id": "id-1",
            },
            "content": "first",
        },
        {
            "source": {
                "title": "B",
                "notebook": "dist/other",
                "external_id": "id-2",
            },
            "content": "second",
        },
        {
            "source": {
                "title": "C",
                "notebook": "dist/other",
                "external_id": "id-1",
            },
            "content": "duplicate external id",
        },
    ]

    external_ids, notebooks = _extract_source_fields(content)

    assert external_ids == ["id-1", "id-2"]
    assert notebooks == ["dist/stream", "dist/other"]
