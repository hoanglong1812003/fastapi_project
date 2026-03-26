"""
db.py — Database connection pool (PostgreSQL via asyncpg).

CHANGES FROM SQLITE:
- Single connection per request  ->  connection pool (min=2, max=10)
- aiosqlite.connect()            ->  asyncpg.create_pool()
- get_db() yields a Connection   ->  get_db() yields a connection from the pool
- Pool is created once at startup and closed at shutdown via lifespan

APPLIED CONCEPTS:
- [Package Management - uv] : asyncpg managed via pyproject.toml + uv sync.
- [Error Handling]           : try/finally guarantees connection is released
                               back to the pool after every request.
"""

import logging
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Module-level pool — initialised in init_db(), shared across all requests
_pool: asyncpg.Pool | None = None

_CREATE_IMAGES_TABLE = """
CREATE TABLE IF NOT EXISTS images (
    id        SERIAL PRIMARY KEY,
    filename  TEXT   NOT NULL,
    content   TEXT   NOT NULL,
    url       TEXT   NOT NULL,
    file_id   TEXT   NOT NULL
)
"""


async def init_db() -> None:
    """
    Called once at application startup.
    Creates the connection pool and ensures the images table exists.
    """
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=2,
        max_size=10,
    )
    async with _pool.acquire() as conn:
        await conn.execute(_CREATE_IMAGES_TABLE)
    logger.info("PostgreSQL pool created — connected to %s", DATABASE_URL.split("@")[-1])


async def close_db() -> None:
    """Called at application shutdown to gracefully close all pool connections."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("PostgreSQL pool closed")


async def get_db() -> asyncpg.Connection:
    """
    FastAPI dependency — acquires a connection from the pool for one request.
    try/finally guarantees the connection is released back to the pool
    even if an exception occurs during the request.
    """
    async with _pool.acquire() as conn:
        yield conn
