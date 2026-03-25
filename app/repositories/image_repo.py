"""
repositories/image_repo.py — Database access layer.

WHY THIS LAYER EXISTS:
    The repository is the ONLY place that writes raw SQL.
    Services call repository functions by name — they never see a query string.
    Swapping SQLite for PostgreSQL means rewriting this file only.

APPLIED CONCEPTS:
- [Functional Programming] : _row_to_dict is a pure function (no side effects).
                             row_to_image is a composed transformation: Row → dict → ImageOut.
                             list_images uses a list comprehension as a map pipeline.
- [Error Handling]         : All DB calls propagate exceptions upward;
                             the service layer decides how to handle them.
- [Package Management - uv]: aiosqlite managed via uv.
"""

from typing import Callable
import aiosqlite

from app.schemas import ImageOut


# ── Pure transformation functions ─────────────────────────────────────────────

def _row_to_dict(row: aiosqlite.Row) -> dict:
    """
    Pure function: converts a sqlite3.Row to a plain dict.
    No side effects — same input always produces same output.
    """
    return dict(zip(row.keys(), tuple(row)))


# Composed transformation pipeline: Row → dict → ImageOut
# Named so every caller uses the same pipeline — one place to change.
row_to_image: Callable[[aiosqlite.Row], ImageOut] = lambda r: ImageOut(**_row_to_dict(r))


# ── Repository functions ───────────────────────────────────────────────────────

async def get_all(
    db: aiosqlite.Connection,
    limit: int,
    offset: int,
) -> list[ImageOut]:
    """
    Fetch a paginated page of images, newest first.

    [List Comprehension] maps every row through the row_to_image pipeline.
    """
    rows = await (await db.execute(
        "SELECT * FROM images ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )).fetchall()
    return [row_to_image(r) for r in rows]  # [List Comprehension]


async def get_by_id(db: aiosqlite.Connection, image_id: int) -> ImageOut | None:
    """Return a single ImageOut or None if the ID does not exist."""
    row = await (await db.execute(
        "SELECT * FROM images WHERE id = ?", (image_id,)
    )).fetchone()
    return row_to_image(row) if row else None


async def insert(
    db: aiosqlite.Connection,
    filename: str,
    content: str,
    url: str,
    file_id: str,
) -> ImageOut:
    """Insert a new image record and return the created ImageOut."""
    cur = await db.execute(
        "INSERT INTO images (filename, content, url, file_id) VALUES (?, ?, ?, ?)",
        (filename, content, url, file_id),
    )
    await db.commit()
    row = await (await db.execute(
        "SELECT * FROM images WHERE id = ?", (cur.lastrowid,)
    )).fetchone()
    return row_to_image(row)


async def update_content(
    db: aiosqlite.Connection,
    image_id: int,
    content: str,
) -> ImageOut | None:
    """Update caption and return the updated ImageOut, or None if not found."""
    await db.execute(
        "UPDATE images SET content = ? WHERE id = ?", (content, image_id)
    )
    await db.commit()
    return await get_by_id(db, image_id)


async def delete(db: aiosqlite.Connection, image_id: int) -> bool:
    """Delete a record. Returns True if a row was deleted, False if not found."""
    cur = await db.execute(
        "DELETE FROM images WHERE id = ?", (image_id,)
    )
    await db.commit()
    return cur.rowcount > 0


async def get_file_id(db: aiosqlite.Connection, image_id: int) -> str | None:
    """Return only the ImageKit file_id for a given image, or None."""
    row = await (await db.execute(
        "SELECT file_id FROM images WHERE id = ?", (image_id,)
    )).fetchone()
    return row["file_id"] if row else None
