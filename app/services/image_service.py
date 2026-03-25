"""
services/image_service.py — Business logic layer.

WHY THIS LAYER EXISTS:
    The service knows the rules of the application.
    It does NOT know what HTTP status codes are — that is the router's job.
    It does NOT write SQL — that is the repository's job.
    This means you can test every business rule without a web server or a database.

APPLIED CONCEPTS:
- [Match/Case]             : MIME type validation — clean alternative to if/elif chains.
- [Functional Programming] : Each step in upload_image is a named function with
                             a single responsibility, forming a readable pipeline.
- [Error Handling]         : Raises typed exceptions (InvalidFileError, StorageError, etc.)
                             The router catches them; the global handler formats them.
- [f-string]               : All dynamic messages use f-strings.
- [Package Management - uv]: imagekitio and python-dotenv managed via uv.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import UploadFile
from imagekitio import ImageKit

import aiosqlite

from app.exceptions import FileTooLargeError, ImageNotFoundError, InvalidFileError, StorageError
from app.repositories import image_repo
from app.schemas import ImageOut

load_dotenv()

logger = logging.getLogger(__name__)

# [Package Management - uv] imagekitio v5 — only private_key needed
_imagekit = ImageKit(private_key=os.getenv("IMAGEKIT_PRIVATE_KEY"))

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_FILE_MB    = MAX_FILE_BYTES // (1024 * 1024)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}


# ── Validation (pure functions — no side effects) ─────────────────────────────

def _validate_mime(file: UploadFile) -> None:
    """
    [Match/Case] Validate the MIME type reported by the client.
    Raises InvalidFileError for non-image content types.
    """
    match file.content_type:
        case ct if ct and ct.startswith("image/"):
            pass
        case _:
            raise InvalidFileError("Only image files are allowed")


def _validate_extension(filename: str) -> None:
    """
    Validate the file extension against an explicit allowlist.
    Prevents clients from bypassing MIME checks with a renamed file.
    """
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileError(f"Extension '{ext}' is not allowed")


def _validate_size(raw: bytes) -> None:
    """Raise FileTooLargeError if the file exceeds MAX_FILE_BYTES."""
    if len(raw) > MAX_FILE_BYTES:
        raise FileTooLargeError(MAX_FILE_MB)


# ── ImageKit calls (isolated side effects) ────────────────────────────────────

def _upload_to_imagekit(raw: bytes, filename: str):
    """
    Upload raw bytes to ImageKit.
    Isolated into its own function so it can be mocked in tests.
    Raises StorageError on any ImageKit failure.
    """
    try:
        return _imagekit.files.upload(
            file=raw,
            file_name=filename,
            use_unique_file_name=True,
        )
    except Exception as e:
        logger.error("ImageKit upload failed: %s", e, exc_info=True)
        raise StorageError("Image upload service unavailable")


def _delete_from_imagekit(file_id: str) -> None:
    """
    Delete a file from ImageKit by its file_id.
    Raises StorageError on failure.
    """
    try:
        _imagekit.files.delete(file_id)
    except Exception as e:
        logger.error("ImageKit delete failed for file_id=%s: %s", file_id, e, exc_info=True)
        raise StorageError("Image delete service unavailable")


# ── Service functions (orchestration pipeline) ────────────────────────────────

async def create_image(
    file: UploadFile,
    caption: str,
    db: aiosqlite.Connection,
) -> ImageOut:
    """
    Upload pipeline — each step is a named function with one responsibility:
        1. validate MIME type       (pure)
        2. validate extension       (pure)
        3. read bytes               (I/O)
        4. validate size            (pure)
        5. upload to ImageKit       (external side effect)
        6. persist to database      (DB side effect)

    [Functional Programming] The pipeline reads like a sentence.
    Each step can be tested independently.
    """
    _validate_mime(file)
    _validate_extension(file.filename or "")

    raw = await file.read()
    _validate_size(raw)

    result = _upload_to_imagekit(raw, file.filename or "upload")

    return await image_repo.insert(
        db,
        filename=file.filename or "upload",
        content=caption,
        url=result.url,
        file_id=result.file_id,
    )


async def list_images(
    db: aiosqlite.Connection,
    limit: int,
    offset: int,
) -> list[ImageOut]:
    """Return a paginated list of images, newest first."""
    return await image_repo.get_all(db, limit=limit, offset=offset)


async def get_image(db: aiosqlite.Connection, image_id: int) -> ImageOut:
    """Return a single image or raise ImageNotFoundError."""
    image = await image_repo.get_by_id(db, image_id)
    if image is None:
        raise ImageNotFoundError(image_id)
    return image


async def update_image(
    db: aiosqlite.Connection,
    image_id: int,
    content: str,
) -> ImageOut:
    """Update caption. Raises ImageNotFoundError if the image does not exist."""
    # Verify existence first
    await get_image(db, image_id)
    updated = await image_repo.update_content(db, image_id, content)
    if updated is None:
        raise ImageNotFoundError(image_id)
    return updated


async def delete_image(db: aiosqlite.Connection, image_id: int) -> None:
    """
    Delete image from ImageKit first, then remove from DB.
    Order matters: if DB delete fails after ImageKit delete, the record
    becomes an orphan — acceptable trade-off for SQLite; use a transaction
    with compensating action for PostgreSQL.
    """
    file_id = await image_repo.get_file_id(db, image_id)
    if file_id is None:
        raise ImageNotFoundError(image_id)

    _delete_from_imagekit(file_id)

    await image_repo.delete(db, image_id)
    logger.info("Deleted image id=%d file_id=%s", image_id, file_id)
