"""
services/image_service.py — Business logic layer.

CHANGES FROM SQLITE VERSION:
- aiosqlite.Connection   ->  asyncpg.Connection
- ImageKit SDK calls wrapped in asyncio.to_thread() to avoid blocking the
  event loop (imagekitio v5 is a synchronous SDK)

APPLIED CONCEPTS:
- [Match/Case]             : MIME type validation.
- [Functional Programming] : Named single-responsibility steps form a readable pipeline.
- [Error Handling]         : Raises typed exceptions — never HTTP status codes.
- [f-string]               : All dynamic messages use f-strings.
- [Package Management - uv]: imagekitio, python-dotenv managed via uv.
"""

import asyncio
import logging
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from fastapi import UploadFile
from imagekitio import ImageKit

from app.exceptions import FileTooLargeError, ImageNotFoundError, InvalidFileError, StorageError
from app.repositories import image_repo
from app.schemas import ImageOut

load_dotenv()

logger = logging.getLogger(__name__)

_imagekit = ImageKit(private_key=os.getenv("IMAGEKIT_PRIVATE_KEY"))

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILE_MB    = MAX_FILE_BYTES // (1024 * 1024)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}


# ── Validation — pure functions ───────────────────────────────────────────────

def _validate_mime(file: UploadFile) -> None:
    """[Match/Case] Reject non-image MIME types."""
    match file.content_type:
        case ct if ct and ct.startswith("image/"):
            pass
        case _:
            raise InvalidFileError("Only image files are allowed")


def _validate_extension(filename: str) -> None:
    """Reject extensions not in the explicit allowlist."""
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileError(f"Extension '{ext}' is not allowed")


def _validate_size(raw: bytes) -> None:
    """Reject files exceeding MAX_FILE_BYTES."""
    if len(raw) > MAX_FILE_BYTES:
        raise FileTooLargeError(MAX_FILE_MB)


# ── ImageKit — isolated side effects ─────────────────────────────────────────

async def _upload_to_imagekit(raw: bytes, filename: str):
    """
    Upload bytes to ImageKit.
    asyncio.to_thread() runs the synchronous SDK call in a thread pool,
    preventing it from blocking the async event loop.
    """
    try:
        return await asyncio.to_thread(
            lambda: _imagekit.files.upload(
                file=raw,
                file_name=filename,
                use_unique_file_name=True,
            )
        )
    except Exception as e:
        logger.error("ImageKit upload failed: %s", e, exc_info=True)
        raise StorageError("Image upload service unavailable")


async def _delete_from_imagekit(file_id: str) -> None:
    """
    Delete a file from ImageKit.
    asyncio.to_thread() prevents blocking the event loop.
    """
    try:
        await asyncio.to_thread(lambda: _imagekit.files.delete(file_id))
    except Exception as e:
        logger.error("ImageKit delete failed for file_id=%s: %s", file_id, e, exc_info=True)
        raise StorageError("Image delete service unavailable")


# ── Service functions — orchestration pipeline ────────────────────────────────

async def create_image(
    file: UploadFile,
    caption: str,
    conn: asyncpg.Connection,
) -> ImageOut:
    """
    Upload pipeline:
        1. validate MIME        (pure)
        2. validate extension   (pure)
        3. read bytes           (async I/O)
        4. validate size        (pure)
        5. upload to ImageKit   (async, thread pool)
        6. insert into DB       (async)
    """
    _validate_mime(file)
    _validate_extension(file.filename or "")

    raw = await file.read()
    _validate_size(raw)

    result = await _upload_to_imagekit(raw, file.filename or "upload")

    return await image_repo.insert(
        conn,
        filename=file.filename or "upload",
        content=caption,
        url=result.url,
        file_id=result.file_id,
    )


async def list_images(
    conn: asyncpg.Connection,
    limit: int,
    offset: int,
) -> list[ImageOut]:
    return await image_repo.get_all(conn, limit=limit, offset=offset)


async def get_image(conn: asyncpg.Connection, image_id: int) -> ImageOut:
    image = await image_repo.get_by_id(conn, image_id)
    if image is None:
        raise ImageNotFoundError(image_id)
    return image


async def update_image(
    conn: asyncpg.Connection,
    image_id: int,
    content: str,
) -> ImageOut:
    updated = await image_repo.update_content(conn, image_id, content)
    if updated is None:
        raise ImageNotFoundError(image_id)
    return updated


async def delete_image(conn: asyncpg.Connection, image_id: int) -> None:
    """Delete from ImageKit first, then remove from DB."""
    file_id = await image_repo.get_file_id(conn, image_id)
    if file_id is None:
        raise ImageNotFoundError(image_id)

    await _delete_from_imagekit(file_id)
    await image_repo.delete(conn, image_id)
    logger.info("Deleted image id=%d file_id=%s", image_id, file_id)
