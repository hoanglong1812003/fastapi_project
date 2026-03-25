"""
KIẾN THỨC ÁP DỤNG:
- [Package Management - uv]     : imagekitio, fastapi, aiosqlite được quản lý qua pyproject.toml + uv sync
- [Match/Case]                   : validate content_type của file upload (dòng ~40)
- [Error Handling]               : try/except bọc ImageKit calls, HTTPException cho 400/404/502
- [f-string]                     : tất cả error message dùng f-string
- [Functional Programming]       : _row_to_dict là pure function; list comprehension trong list_images

BẢO MẬT ÁP DỤNG:
- [File type validation]         : Match/Case kiểm tra MIME type, từ chối non-image
- [File size limit]              : Giới hạn 10MB server-side
- [Parameterized queries]        : Dùng ? placeholder, tránh SQL injection
- [No sensitive data in response]: file_id (ImageKit internal) không expose ra ngoài qua ImageOut nếu cần ẩn
"""

import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from imagekitio import ImageKit

import aiosqlite
from app.db import get_db
from app.schemas import ImageOut

load_dotenv()

# [Package Management - uv] imagekitio được cài qua uv, khởi tạo chỉ cần private_key (v5 API)
imagekit = ImageKit(private_key=os.getenv("IMAGEKIT_PRIVATE_KEY"))

router = APIRouter(prefix="/images", tags=["images"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB — [Security] giới hạn upload size

# [Functional Programming] pure function chuyển aiosqlite.Row → dict
def _row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(zip(row.keys(), row))


# ── Upload ────────────────────────────────────────────────────────────────────
@router.post("/", response_model=ImageOut, status_code=201)
async def upload_image(
    content: str = Form(...),
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    # [Match/Case] validate MIME type — chỉ chấp nhận image/*
    match file.content_type:
        case ct if ct and ct.startswith("image/"):
            pass
        case _:
            raise HTTPException(400, "Only image files are allowed")  # [Error Handling]

    raw = await file.read()

    # [Security] kiểm tra kích thước file server-side
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File vượt quá {MAX_FILE_SIZE // (1024*1024)}MB")  # [f-string]

    # [Error Handling] bọc ImageKit upload, trả 502 nếu lỗi bên thứ 3
    try:
        result = imagekit.files.upload(
            file=raw,
            file_name=file.filename,
            use_unique_file_name=True,
        )
    except Exception as e:
        raise HTTPException(502, f"ImageKit upload failed: {e}")  # [f-string]

    url     = result.url
    file_id = result.file_id

    # [Security] parameterized query — tránh SQL injection
    cur = await db.execute(
        "INSERT INTO images (filename, content, url, file_id) VALUES (?,?,?,?)",
        (file.filename, content, url, file_id),
    )
    await db.commit()
    row = await (await db.execute(
        "SELECT * FROM images WHERE id=?", (cur.lastrowid,)
    )).fetchone()
    return ImageOut(**_row_to_dict(row))  # [Functional Programming] unpack dict


# ── List all ──────────────────────────────────────────────────────────────────
@router.get("/", response_model=list[ImageOut])
async def list_images(db: aiosqlite.Connection = Depends(get_db)):
    rows = await (await db.execute("SELECT * FROM images ORDER BY id DESC")).fetchall()
    # [List Comprehension] + [Functional Programming] map rows → ImageOut
    return [ImageOut(**_row_to_dict(r)) for r in rows]


# ── Get one ───────────────────────────────────────────────────────────────────
@router.get("/{image_id}", response_model=ImageOut)
async def get_image(image_id: int, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute(
        "SELECT * FROM images WHERE id=?", (image_id,)  # [Security] parameterized
    )).fetchone()
    if not row:
        raise HTTPException(404, f"Image {image_id} not found")  # [Error Handling] [f-string]
    return ImageOut(**_row_to_dict(row))


# ── Update content ────────────────────────────────────────────────────────────
@router.patch("/{image_id}", response_model=ImageOut)
async def update_image(
    image_id: int,
    content: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    row = await (await db.execute(
        "SELECT * FROM images WHERE id=?", (image_id,)
    )).fetchone()
    if not row:
        raise HTTPException(404, f"Image {image_id} not found")  # [Error Handling] [f-string]

    await db.execute(
        "UPDATE images SET content=? WHERE id=?", (content, image_id)  # [Security] parameterized
    )
    await db.commit()
    row = await (await db.execute(
        "SELECT * FROM images WHERE id=?", (image_id,)
    )).fetchone()
    return ImageOut(**_row_to_dict(row))


# ── Delete ────────────────────────────────────────────────────────────────────
@router.delete("/{image_id}", status_code=204)
async def delete_image(image_id: int, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute(
        "SELECT * FROM images WHERE id=?", (image_id,)
    )).fetchone()
    if not row:
        raise HTTPException(404, f"Image {image_id} not found")  # [Error Handling] [f-string]

    # [Error Handling] bọc ImageKit delete, trả 502 nếu lỗi
    try:
        imagekit.files.delete(row["file_id"])
    except Exception as e:
        raise HTTPException(502, f"ImageKit delete failed: {e}")  # [f-string]

    await db.execute("DELETE FROM images WHERE id=?", (image_id,))  # [Security] parameterized
    await db.commit()
