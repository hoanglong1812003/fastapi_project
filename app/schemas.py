"""
schemas.py — Pydantic models for request validation and response serialisation.

APPLIED CONCEPTS:
- [Functional Programming] : ImageOut is an immutable data container.
                             ImageCreate enforces strict input constraints via Field.
- [Package Management - uv]: pydantic is bundled with fastapi, managed via uv.
"""

from pydantic import BaseModel, Field


class ImageCreate(BaseModel):
    """
    Input validation for caption text.
    Pydantic rejects the request before it reaches the service layer
    if content is empty or exceeds 500 characters.
    """
    content: str = Field(..., min_length=1, max_length=500)


class ImageOut(BaseModel):
    """
    Response model — defines exactly what the API exposes to clients.
    file_id is included so the frontend can reference ImageKit assets if needed.
    """
    id:       int
    filename: str
    content:  str
    url:      str
    file_id:  str
