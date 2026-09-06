"""Node API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response

from assistant.api.dependencies import CurrentUser, SessionDep, StorageDep
from assistant.api.schemas.nodes import (
    NodeCreate,
    NodePatch,
    NodeResponse,
    NodeSplit,
    NodeUpdate,
    SplitResponse,
)
from assistant.attachments.service import delete_file_record
from assistant.models.schema import Node
from assistant.notes.exceptions import NodeNotFoundError
from assistant.notes.service import (
    add_attachment_node,
    add_markdown_node,
    add_text_node,
    delete_node,
    get_node_in_note,
    get_ordered_nodes,
    insert_markdown_node,
    insert_text_node,
    merge_text_nodes,
    split_text_node,
    update_markdown_node,
    update_text_node,
    validate_node_in_note,
    validate_note_in_notebook,
)

router = APIRouter()


@router.get(
    "/{notebook_id}/note/{note_id}/node",
    response_model=list[NodeResponse],
)
def list_nodes_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> list[NodeResponse]:
    """List all nodes in a note, ordered by position."""
    validate_note_in_notebook(session, notebook_id, note_id)
    nodes = get_ordered_nodes(session, note_id, caller=user)
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
    user: CurrentUser,
) -> NodeResponse:
    """Create a node in a note, optionally positioned between neighbours."""
    validate_note_in_notebook(session, notebook_id, note_id)

    if body.file_id is not None:
        try:
            node = add_attachment_node(session, note_id, user, body.file_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return NodeResponse.model_validate(node)

    if body.payload is None:
        raise HTTPException(
            status_code=422,
            detail="payload is required when file_id is not set",
        )

    has_neighbors = body.after_node_id is not None or body.before_node_id is not None
    if body.block_type is not None:
        if has_neighbors:
            node = insert_markdown_node(
                session,
                note_id=note_id,
                author=user,
                payload=body.payload,
                block_type=body.block_type,
                after_node_id=body.after_node_id,
                before_node_id=body.before_node_id,
            )
        else:
            node = add_markdown_node(
                session,
                note_id=note_id,
                author=user,
                payload=body.payload,
                block_type=body.block_type,
            )
    elif has_neighbors:
        node = insert_text_node(
            session,
            note_id=note_id,
            author=user,
            payload=body.payload,
            after_node_id=body.after_node_id,
            before_node_id=body.before_node_id,
        )
    else:
        node = add_text_node(
            session,
            note_id=note_id,
            author=user,
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
    user: CurrentUser,
) -> NodeResponse:
    """Update a node's payload or merge another node into it."""
    get_node_in_note(session, notebook_id, note_id, node_id)
    if isinstance(body, NodeUpdate):
        if body.block_type is not None:
            node = update_markdown_node(
                session,
                node_id=node_id,
                caller=user,
                payload=body.payload,
                block_type=body.block_type,
                expected_version=body.expected_version,
            )
        else:
            node = update_text_node(
                session,
                node_id=node_id,
                caller=user,
                payload=body.payload,
                expected_version=body.expected_version,
            )
    else:
        validate_node_in_note(session, note_id, body.source_node_id)
        node = merge_text_nodes(
            session,
            node_id=body.source_node_id,
            caller=user,
            merge_into_id=node_id,
            expected_version_node=body.source_expected_version,
            expected_version_target=body.expected_version,
        )
    return NodeResponse.model_validate(node)


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
    user: CurrentUser,
) -> SplitResponse:
    """Split a text node at a character offset, producing two nodes."""
    get_node_in_note(session, notebook_id, note_id, node_id)
    original, new = split_text_node(
        session,
        node_id=node_id,
        author=user,
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
def delete_node_endpoint(  # noqa: PLR0913
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    node_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
) -> Response:
    """Delete a node. Idempotent — returns 204 whether or not the node existed."""
    validate_note_in_notebook(session, notebook_id, note_id)
    node = session.get(Node, node_id)
    if node is not None and node.note_id != note_id:
        raise NodeNotFoundError(str(node_id))
    file_id = delete_node(session, node_id, caller=user)
    if file_id is not None:
        delete_file_record(session, storage, file_id)
    return Response(status_code=204)
