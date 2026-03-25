"""
app.py — Application factory.

Responsibilities:
    - Configure logging
    - Register global exception handlers (one place for all error formatting)
    - Attach rate limiter
    - Mount routers
    - Expose health check and UI route

APPLIED CONCEPTS:
- [Error Handling]         : Global handlers convert typed exceptions → HTTP responses.
                             Changing the error format means editing this file only.
- [Package Management - uv]: slowapi, fastapi, jinja2 managed via uv.
"""

import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.db import init_db
from app.exceptions import FileTooLargeError, ImageNotFoundError, InvalidFileError, StorageError
from app.routers.images import router as images_router

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
# [Package Management - uv] slowapi managed via uv
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── Templates ─────────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    logger.info("Application startup complete")
    yield
    logger.info("Application shutdown")


# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="PicFeed",
    description="Lightweight social image-sharing API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.include_router(images_router)


# ── Global exception handlers ─────────────────────────────────────────────────
# Each handler converts one typed exception into a consistent JSON response.
# Routes and services never touch HTTPException or status codes directly.

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
    """Health check endpoint — used by load balancers and container orchestrators."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
