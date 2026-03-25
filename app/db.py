"""
db.py — Database connection and table initialisation.

APPLIED CONCEPTS:
- [Package Management - uv] : aiosqlite managed via pyproject.toml + uv sync.
- [Error Handling]           : try/finally guarantees db.close() is always called,
                               even if an exception occurs mid-request.
"""

import logging
import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = "images.db"

_CREATE_IMAGES_TABLE = """
CREATE TABLE IF NOT EXISTS images (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT    NOT NULL,
    content  TEXT    NOT NULL,
    url      TEXT    NOT NULL,
    file_id  TEXT    NOT NULL
)
"""


async def get_db():
    """
    FastAPI dependency that yields an open DB connection per request.
    try/finally ensures the connection is closed regardless of what happens.
    """
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    """Called once at application startup to create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_CREATE_IMAGES_TABLE)
        await db.commit()
    logger.info("Database initialised at '%s'", DB_PATH)
