"""API routes implemented in Rust."""

from __future__ import annotations

from typing import Annotated

from assistant_rust import greet
from fastapi import APIRouter, Query

from assistant.api.dependencies import CurrentUser
from assistant.api.schemas.rustcore import GreetingResponse

router = APIRouter()


# `def`, not `async def`: FastAPI runs it in a thread pool, which keeps the Rust
# call off the event loop.
@router.get("/greeting", response_model=GreetingResponse)
def greeting_endpoint(
    name: Annotated[str, Query(min_length=1)],
    _user: CurrentUser,
) -> GreetingResponse:
    return GreetingResponse(message=greet(name))
