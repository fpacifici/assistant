"""Shared pagination parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query


@dataclass(frozen=True)
class PaginationParams:
    offset: int
    limit: int


def pagination_params(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginationParams:
    return PaginationParams(offset=offset, limit=limit)


Pagination = Annotated[PaginationParams, Depends(pagination_params)]
