"""
app.py — Application factory.

Responsibilities:
    - Configure logging
    - Register global exception handlers
    - Attach rate limiter
    - Mount routers
    - Manage DB pool lifecycle (startup / shutdown)
    - Expose health check and UI route
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.db import close_db, init_db
from app.exceptions import FileTooLargeError, ImageNotFoundError, InvalidFileError, StorageError
from app.routers.images import router as images_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── Templates ─────────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# ── Lifespan — pool created on startup, closed on shutdown ───────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    logger.info("Application startup complete")
    yield
    await close_db()
    logger.info("Application shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="PicFeed",
    description="Lightweight social image-sharing API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.include_router(images_router)


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please slow down."})


@app.exception_handler(ImageNotFoundError)
async def image_not_found_handler(request: Request, exc: ImageNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InvalidFileError)
async def invalid_file_handler(request: Request, exc: InvalidFileError):
    return JSONResponse(status_code=400, content={"detail": exc.detail})


@app.exception_handler(FileTooLargeError)
async def file_too_large_handler(request: Request, exc: FileTooLargeError):
    return JSONResponse(status_code=413, content={"detail": str(exc)})


@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
