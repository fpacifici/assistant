"""API routes implemented in Go."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from assistant.api.dependencies import CurrentUser
from assistant.api.schemas.gocore import GreetingResponse
from assistant.golib import greet

router = APIRouter()


# `def`, not `async def`: FastAPI runs it in a thread pool, which keeps the Go
# call off the event loop.
@router.get("/greeting", response_model=GreetingResponse)
def greeting_endpoint(
    name: Annotated[str, Query(min_length=1)],
    _user: CurrentUser,
) -> GreetingResponse:
    return GreetingResponse(message=greet(name))
