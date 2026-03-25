"""
routers/images.py — HTTP routing layer.

WHY THIS LAYER EXISTS:
    The router's ONLY job is to:
        1. Parse the incoming HTTP request.
        2. Call the appropriate service function.
        3. Return the HTTP response.

    It does NOT write SQL. It does NOT call ImageKit directly.
    It does NOT contain business rules.

APPLIED CONCEPTS:
- [Error Handling]         : Catches typed service exceptions and re-raises as HTTPException.
                             Global handlers in app.py handle ImageNotFoundError / StorageError
                             automatically — no manual HTTPException needed for those.
- [Package Management - uv]: fastapi managed via uv.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

import aiosqlite

from app.db import get_db
from app.schemas import ImageOut
from app.services import image_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/", response_model=ImageOut, status_code=201)
async def upload_image(
    request: Request,
    content: str = Form(..., min_length=1, max_length=500),
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await image_service.create_image(file, content, db)


@router.get("/", response_model=list[ImageOut])
async def list_images(
    db: aiosqlite.Connection = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await image_service.list_images(db, limit=limit, offset=offset)


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(
    image_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    return await image_service.get_image(db, image_id)


@router.patch("/{image_id}", response_model=ImageOut)
async def update_image(
    image_id: int,
    content: str = Form(..., min_length=1, max_length=500),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await image_service.update_image(db, image_id, content)


@router.delete("/{image_id}", status_code=204)
async def delete_image(
    image_id: int,
    db: aiosqlite.Connection = Depends(get_db),
):
    await image_service.delete_image(db, image_id)
