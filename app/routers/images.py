"""
routers/images.py — HTTP routing layer.

The router's only job: parse request → call service → return response.
No SQL, no ImageKit, no business rules.
"""

import logging

import asyncpg
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

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
    conn: asyncpg.Connection = Depends(get_db),
):
    return await image_service.create_image(file, content, conn)


@router.get("/", response_model=list[ImageOut])
async def list_images(
    conn: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await image_service.list_images(conn, limit=limit, offset=offset)


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(
    image_id: int,
    conn: asyncpg.Connection = Depends(get_db),
):
    return await image_service.get_image(conn, image_id)


@router.patch("/{image_id}", response_model=ImageOut)
async def update_image(
    image_id: int,
    content: str = Form(..., min_length=1, max_length=500),
    conn: asyncpg.Connection = Depends(get_db),
):
    return await image_service.update_image(conn, image_id, content)


@router.delete("/{image_id}", status_code=204)
async def delete_image(
    image_id: int,
    conn: asyncpg.Connection = Depends(get_db),
):
    await image_service.delete_image(conn, image_id)
