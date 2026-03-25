# PicFeed

A lightweight social image-sharing web application built with FastAPI. Users can upload images with captions, view a feed of all posts, edit captions, and delete posts. Images are stored on ImageKit.io while metadata is persisted in a local SQLite database.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Security Measures](#security-measures)
- [Applied Concepts](#applied-concepts)

---

## Features

- Upload images with a caption via drag-and-drop or file picker
- View all posts in a reverse-chronological feed
- Edit the caption of any existing post inline
- Delete a post, which removes it from both the database and ImageKit.io
- Client-side image preview before submitting
- Toast notifications for all user actions
- Fully responsive dark-themed UI

---

## Tech Stack

| Layer       | Technology                          |
|-------------|-------------------------------------|
| Backend     | FastAPI, Uvicorn                    |
| Database    | SQLite via aiosqlite (async)        |
| Storage     | ImageKit.io (imagekitio v5)         |
| Templating  | Jinja2                              |
| Frontend    | Vanilla HTML / CSS / JavaScript     |
| Environment | python-dotenv                       |
| Package Mgr | uv                                  |

---

## Project Structure

```
fastapi_project/
├── app/
│   ├── app.py          # FastAPI application, lifespan, template route
│   ├── db.py           # Database connection, table initialization
│   ├── images.py       # CRUD router for images
│   ├── schemas.py      # Pydantic response model
│   └── templates/
│       └── index.html  # Frontend UI
├── main.py             # Entry point (uvicorn runner)
├── pyproject.toml      # Project metadata and dependencies (uv)
├── .env                # Environment variables (not committed)
└── images.db           # SQLite database (auto-created on first run)
```

---

## Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- An [ImageKit.io](https://imagekit.io) account with API credentials

---

## Installation

**1. Clone the repository**

```bash
git clone <repository-url>
cd fastapi_project
```

**2. Install dependencies using uv**

```bash
uv sync
```

This reads `pyproject.toml` and installs all required packages into an isolated virtual environment automatically.

---

## Configuration

Create a `.env` file in the project root with the following variables:

```env
IMAGEKIT_PRIVATE_KEY=your_private_key_here
IMAGEKIT_PUBLIC_KEY=your_public_key_here
IMAGEKIT_URL=https://ik.imagekit.io/your_imagekit_id
```

These credentials can be found in your ImageKit.io dashboard under **Developer Options**.

> The `.env` file is listed in `.gitignore` and should never be committed to version control.

---

## Running the Application

```bash
uv run python main.py
```

The server starts at `http://localhost:8000` with hot-reload enabled.

- Web UI:      http://localhost:8000
- API Docs:    http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc

The SQLite database (`images.db`) is created automatically on first run.

---

## API Reference

All endpoints are prefixed with `/images`.

| Method   | Endpoint          | Description                        | Body (multipart/form-data)     |
|----------|-------------------|------------------------------------|--------------------------------|
| `GET`    | `/images/`        | Retrieve all images (newest first) | —                              |
| `GET`    | `/images/{id}`    | Retrieve a single image by ID      | —                              |
| `POST`   | `/images/`        | Upload a new image with caption    | `file` (image), `content` (str)|
| `PATCH`  | `/images/{id}`    | Update the caption of an image     | `content` (str)                |
| `DELETE` | `/images/{id}`    | Delete image from DB and ImageKit  | —                              |

**Response schema (`ImageOut`)**

```json
{
  "id":       1,
  "filename": "photo.jpg",
  "content":  "Caption text here",
  "url":      "https://ik.imagekit.io/...",
  "file_id":  "imagekit_file_id"
}
```

**HTTP status codes used**

| Code | Meaning                              |
|------|--------------------------------------|
| 200  | OK                                   |
| 201  | Created                              |
| 204  | No Content (successful delete)       |
| 400  | Bad Request (invalid file type)      |
| 404  | Not Found                            |
| 413  | Payload Too Large (exceeds 10MB)     |
| 502  | Bad Gateway (ImageKit error)         |

---

## Security Measures

| Measure                  | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| MIME type validation     | Server rejects any upload whose `Content-Type` does not start with `image/` |
| File size limit          | Uploads exceeding 10 MB are rejected server-side with HTTP 413              |
| Parameterized SQL queries | All database queries use `?` placeholders, preventing SQL injection         |
| XSS prevention           | Frontend sanitizes all user-generated content before inserting into the DOM |
| Client-side validation   | File type and size are also checked in the browser before the request is sent|
| Environment variables    | All credentials are loaded from `.env` and never hardcoded in source files  |

---

## Applied Concepts

This project was built to demonstrate the following Python concepts:

**Package Management (uv)**
All dependencies are declared in `pyproject.toml` and managed exclusively through `uv sync`. No `pip` or `requirements.txt` is used.

**Match / Case**
Used in the upload endpoint to validate the file's MIME type, providing a clean and readable alternative to if/elif chains.

```python
match file.content_type:
    case ct if ct and ct.startswith("image/"):
        pass
    case _:
        raise HTTPException(400, "Only image files are allowed")
```

**List Comprehensions**
Used to transform database rows into Pydantic response models in a concise, readable way.

```python
return [ImageOut(**_row_to_dict(r)) for r in rows]
```

**Error Handling**
- `try/except` wraps all third-party ImageKit calls to catch network or API errors and return appropriate HTTP responses.
- `try/finally` in `get_db` guarantees the database connection is always closed, even if an exception occurs during a request.

**f-strings**
All dynamic error messages are constructed using f-strings for clarity and performance.

```python
raise HTTPException(404, f"Image {image_id} not found")
```

**Functional Programming**
- `_row_to_dict` is a pure function with no side effects, used to convert database rows to dictionaries.
- `ImageOut` acts as an immutable data container.
- The frontend `renderPost` function is a pure function that maps a data object to an HTML string.
