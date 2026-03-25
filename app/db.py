"""
KIẾN THỨC ÁP DỤNG:
- [Package Management - uv] : aiosqlite được quản lý qua pyproject.toml + uv sync
- [Error Handling]           : try/finally trong get_db đảm bảo connection luôn được đóng
"""

import aiosqlite

DB_PATH = "images.db"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS images (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT    NOT NULL,
    content  TEXT    NOT NULL,
    url      TEXT    NOT NULL,
    file_id  TEXT    NOT NULL
)
"""

# [Error Handling] try/finally đảm bảo db.close() luôn được gọi dù có exception
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TABLE)
        await db.commit()
