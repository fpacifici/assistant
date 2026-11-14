"""Schemas for the Go-backed endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class GreetingResponse(BaseModel):
    message: str
