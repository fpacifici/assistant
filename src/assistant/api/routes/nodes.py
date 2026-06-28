"""Node API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from assistant.api.dependencies import CurrentUserId, SessionDep, require_notebook_owner
from assistant.api.schemas.nodes import (
    NodeCreate,
    NodePatch,
    NodeResponse,
    NodeSplit,
    NodeUpdate,
    SplitResponse,
)
from assistant.models.schema import Node
from assistant.notes.exceptions import NodeNotFoundError, NoteNotFoundError
from assistant.notes.service import (
    add_markdown_node,
    add_text_node,
    delete_node,
    get_note,
    get_ordered_nodes,
    insert_markdown_node,
    insert_text_node,
    merge_text_nodes,
    split_text_node,
    update_markdown_node,
    update_text_node,
)

router = APIRouter()


def _get_node_in_note(
    session: SessionDep,
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    node_id: uuid.UUID,
) -> Node:
    note = get_note(session, note_id)
    if note.notebook_id != notebook_id:
        raise NoteNotFoundError(str(note_id))
    node = session.get(Node, node_id)
    if node is None or node.note_id != note_id:
        raise NodeNotFoundError(str(node_id))
    return node


def _validate_note_in_notebook(
    session: SessionDep,
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
) -> None:
    note = get_note(session, note_id)
    if note.notebook_id != notebook_id:
        raise NoteNotFoundError(str(note_id))


@router.get(
    "/{notebook_id}/note/{note_id}/node",
    response_model=list[NodeResponse],
)
def list_nodes_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
) -> list[NodeResponse]:
    """List all nodes in a note, ordered by position."""
    require_notebook_owner(session, notebook_id, user_id)
    _validate_note_in_notebook(session, notebook_id, note_id)
    nodes = get_ordered_nodes(session, note_id)
    return [NodeResponse.model_validate(n) for n in nodes]


@router.post(
    "/{notebook_id}/note/{note_id}/node",
    status_code=201,
    response_model=NodeResponse,
)
def create_node_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NodeCreate,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NodeResponse:
    """Create a node in a note, optionally positioned between neighbours."""
    require_notebook_owner(session, notebook_id, user_id)
    _validate_note_in_notebook(session, notebook_id, note_id)
    has_neighbors = body.after_node_id is not None or body.before_node_id is not None
    if body.block_type is not None:
        if has_neighbors:
            node = insert_markdown_node(
                session,
                note_id=note_id,
                author_id=user_id,
                payload=body.payload,
                block_type=body.block_type,
                after_node_id=body.after_node_id,
                before_node_id=body.before_node_id,
            )
        else:
            node = add_markdown_node(
                session,
                note_id=note_id,
                author_id=user_id,
                payload=body.payload,
                block_type=body.block_type,
            )
    elif has_neighbors:
        node = insert_text_node(
            session,
            note_id=note_id,
            author_id=user_id,
            payload=body.payload,
            after_node_id=body.after_node_id,
            before_node_id=body.before_node_id,
        )
    else:
        node = add_text_node(
            session,
            note_id=note_id,
            author_id=user_id,
            payload=body.payload,
        )
    return NodeResponse.model_validate(node)


@router.patch(
    "/{notebook_id}/note/{note_id}/node/{node_id}",
    response_model=NodeResponse,
)
def patch_node_endpoint(  # noqa: PLR0913
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    node_id: uuid.UUID,
    body: NodePatch,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NodeResponse:
    """Update a node's payload or merge another node into it."""
    require_notebook_owner(session, notebook_id, user_id)
    _get_node_in_note(session, notebook_id, note_id, node_id)
    if isinstance(body, NodeUpdate):
        if body.block_type is not None:
            node = update_markdown_node(
                session,
                node_id=node_id,
                payload=body.payload,
                block_type=body.block_type,
                expected_version=body.expected_version,
            )
        else:
            node = update_text_node(
                session,
                node_id=node_id,
                payload=body.payload,
                expected_version=body.expected_version,
            )
    else:
        _validate_source_in_note(session, note_id, body.source_node_id)
        node = merge_text_nodes(
            session,
            node_id=body.source_node_id,
            merge_into_id=node_id,
            expected_version_node=body.source_expected_version,
            expected_version_target=body.expected_version,
        )
    return NodeResponse.model_validate(node)


def _validate_source_in_note(
    session: SessionDep,
    note_id: uuid.UUID,
    source_node_id: uuid.UUID,
) -> None:
    source = session.get(Node, source_node_id)
    if source is None or source.note_id != note_id:
        raise NodeNotFoundError(str(source_node_id))


@router.post(
    "/{notebook_id}/note/{note_id}/node/{node_id}/split",
    status_code=201,
    response_model=SplitResponse,
)
def split_node_endpoint(  # noqa: PLR0913
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    node_id: uuid.UUID,
    body: NodeSplit,
    session: SessionDep,
    user_id: CurrentUserId,
) -> SplitResponse:
    """Split a text node at a character offset, producing two nodes."""
    require_notebook_owner(session, notebook_id, user_id)
    _get_node_in_note(session, notebook_id, note_id, node_id)
    original, new = split_text_node(
        session,
        node_id=node_id,
        author_id=user_id,
        split_offset=body.offset,
        expected_version=body.expected_version,
    )
    return SplitResponse(
        original=NodeResponse.model_validate(original),
        new=NodeResponse.model_validate(new),
    )


@router.delete(
    "/{notebook_id}/note/{note_id}/node/{node_id}",
    status_code=204,
)
def delete_node_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    node_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
) -> Response:
    """Delete a node. Idempotent — returns 204 whether or not the node existed."""
    require_notebook_owner(session, notebook_id, user_id)
    _validate_note_in_notebook(session, notebook_id, note_id)
    delete_node(session, node_id)
    return Response(status_code=204)
