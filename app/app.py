from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.db import init_db
from app.images import router as images_router

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

@asynccontextmanager
async def lifespan(_):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(images_router)

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
