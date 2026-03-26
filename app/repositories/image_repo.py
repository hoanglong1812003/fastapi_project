"""
repositories/image_repo.py — Database access layer (PostgreSQL / asyncpg).

CHANGES FROM SQLITE:
- aiosqlite.Row          ->  asyncpg.Record  (supports dict(record) directly)
- ? placeholders         ->  $1, $2, ...     (PostgreSQL parameterized syntax)
- cursor.lastrowid       ->  RETURNING id    (PostgreSQL way to get inserted ID)
- fetchall()             ->  fetch()
- fetchone()             ->  fetchrow()

APPLIED CONCEPTS:
- [Functional Programming] : _record_to_dict is a pure function.
                             row_to_image is a composed pipeline: Record -> dict -> ImageOut.
                             get_all uses a list comprehension as a map pipeline.
- [Package Management - uv]: asyncpg managed via uv.
"""

from typing import Callable

import asyncpg

from app.schemas import ImageOut


# ── Pure transformation functions ─────────────────────────────────────────────

def _record_to_dict(record: asyncpg.Record) -> dict:
    """
    Pure function: converts an asyncpg.Record to a plain dict.
    asyncpg.Record supports dict() directly — no zip() needed.
    """
    return dict(record)


# Composed pipeline: Record -> dict -> ImageOut
row_to_image: Callable[[asyncpg.Record], ImageOut] = lambda r: ImageOut(**_record_to_dict(r))


# ── Repository functions ───────────────────────────────────────────────────────

async def get_all(
    conn: asyncpg.Connection,
    limit: int,
    offset: int,
) -> list[ImageOut]:
    """Fetch a paginated page of images, newest first."""
    rows = await conn.fetch(
        "SELECT * FROM images ORDER BY id DESC LIMIT $1 OFFSET $2",
        limit, offset,
    )
    return [row_to_image(r) for r in rows]  # [List Comprehension]


async def get_by_id(conn: asyncpg.Connection, image_id: int) -> ImageOut | None:
    """Return a single ImageOut or None if the ID does not exist."""
    row = await conn.fetchrow(
        "SELECT * FROM images WHERE id = $1", image_id
    )
    return row_to_image(row) if row else None


async def insert(
    conn: asyncpg.Connection,
    filename: str,
    content: str,
    url: str,
    file_id: str,
) -> ImageOut:
    """
    Insert a new image record and return the created ImageOut.
    RETURNING * fetches the full row in one round-trip — no second SELECT needed.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO images (filename, content, url, file_id)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        filename, content, url, file_id,
    )
    return row_to_image(row)


async def update_content(
    conn: asyncpg.Connection,
    image_id: int,
    content: str,
) -> ImageOut | None:
    """
    Update caption and return the updated ImageOut.
    RETURNING * avoids a second SELECT round-trip.
    """
    row = await conn.fetchrow(
        "UPDATE images SET content = $1 WHERE id = $2 RETURNING *",
        content, image_id,
    )
    return row_to_image(row) if row else None


async def delete(conn: asyncpg.Connection, image_id: int) -> bool:
    """Delete a record. Returns True if a row was deleted, False if not found."""
    result = await conn.execute(
        "DELETE FROM images WHERE id = $1", image_id
    )
    # asyncpg returns a status string like "DELETE 1" or "DELETE 0"
    return result == "DELETE 1"


async def get_file_id(conn: asyncpg.Connection, image_id: int) -> str | None:
    """Return only the ImageKit file_id for a given image, or None."""
    row = await conn.fetchrow(
        "SELECT file_id FROM images WHERE id = $1", image_id
    )
    return row["file_id"] if row else None
