# PicFeed — Architecture

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Layer Architecture](#layer-architecture)
- [Request Lifecycle](#request-lifecycle)
- [Data Flow](#data-flow)
- [Component Responsibilities](#component-responsibilities)
- [Dependency Graph](#dependency-graph)
- [Error Handling Strategy](#error-handling-strategy)
- [External Integrations](#external-integrations)
- [Security Architecture](#security-architecture)
- [Design Decisions and Trade-offs](#design-decisions-and-trade-offs)

---

## Overview

PicFeed is a lightweight social image-sharing application built with FastAPI. It follows a
**3-layer clean architecture**: Router → Service → Repository. Each layer has a single,
well-defined responsibility and communicates only with the layer directly below it.

```
Client (Browser)
      |
      | HTTP
      v
  [ Router ]        — parse request, return response
      |
      | function calls
      v
  [ Service ]       — business rules, validation, orchestration
      |
      | function calls
      v
  [ Repository ]    — raw SQL, database access only
      |
      | aiosqlite
      v
  [ SQLite DB ]     — images.db
```

The Service layer also communicates with one external system:

```
  [ Service ]
      |
      | imagekitio SDK (HTTP)
      v
  [ ImageKit.io ]   — cloud image storage
```

---

## Project Structure

```
fastapi_project/
|
|-- main.py                         Entry point — starts Uvicorn server
|-- pyproject.toml                  Dependencies managed by uv
|-- .env                            Secrets (never committed)
|-- images.db                       SQLite database (auto-created on startup)
|
`-- app/
    |
    |-- app.py                      Application factory
    |                               Logging, rate limiter, global exception handlers,
    |                               health check, UI route, router registration
    |
    |-- db.py                       Database connection
    |                               get_db() dependency, init_db() startup function
    |
    |-- schemas.py                  Pydantic models
    |                               ImageCreate (input), ImageOut (response)
    |
    |-- exceptions.py               Custom exception types
    |                               ImageNotFoundError, StorageError,
    |                               InvalidFileError, FileTooLargeError
    |
    |-- routers/
    |   `-- images.py               HTTP layer
    |                               Parses requests, calls service, returns responses
    |                               Knows: HTTP methods, status codes, query params
    |                               Does NOT know: SQL, ImageKit, business rules
    |
    |-- services/
    |   `-- image_service.py        Business logic layer
    |                               Validation pipeline, ImageKit orchestration
    |                               Knows: application rules, external APIs
    |                               Does NOT know: HTTP status codes, raw SQL
    |
    |-- repositories/
    |   `-- image_repo.py           Database access layer
    |                               All raw SQL lives here
    |                               Knows: SQL, aiosqlite, table schema
    |                               Does NOT know: HTTP, business rules, ImageKit
    |
    `-- templates/
        `-- index.html              Frontend UI (Jinja2 + Vanilla JS)
                                    Feed, upload form, pagination, edit/delete
```

---

## Layer Architecture

### Layer 1 — Router (`routers/images.py`)

The router is the entry point for every HTTP request. Its job is narrow and explicit:

1. Declare the HTTP method, path, and expected inputs
2. Pass validated inputs to the service
3. Return the service result as an HTTP response

```
POST /images/          ->  image_service.create_image()
GET  /images/          ->  image_service.list_images()
GET  /images/{id}      ->  image_service.get_image()
PATCH /images/{id}     ->  image_service.update_image()
DELETE /images/{id}    ->  image_service.delete_image()
```

The router never writes SQL. It never calls ImageKit. It never contains an if/else
business rule. If you need to add a new endpoint, you add it here and call a service.

---

### Layer 2 — Service (`services/image_service.py`)

The service contains every rule the application enforces. For the upload flow, this is
a sequential pipeline where each step is a named function:

```
create_image()
    |
    |-- _validate_mime()          pure — raises InvalidFileError
    |-- _validate_extension()     pure — raises InvalidFileError
    |-- file.read()               async I/O
    |-- _validate_size()          pure — raises FileTooLargeError
    |-- _upload_to_imagekit()     external side effect — raises StorageError
    `-- image_repo.insert()       DB side effect — returns ImageOut
```

Each step is isolated. Each step can be tested independently without a web server
or a database. The service raises typed exceptions — it never constructs an HTTP
response or a status code.

---

### Layer 3 — Repository (`repositories/image_repo.py`)

The repository is the only place in the codebase that contains raw SQL strings.
If the database changes (e.g. SQLite to PostgreSQL), only this file changes.

Functions exposed:

```
get_all(db, limit, offset)     -> list[ImageOut]
get_by_id(db, image_id)        -> ImageOut | None
insert(db, filename, ...)      -> ImageOut
update_content(db, id, text)   -> ImageOut | None
delete(db, image_id)           -> bool
get_file_id(db, image_id)      -> str | None
```

The repository also owns the two pure transformation functions that form the
data pipeline from raw database rows to typed Python objects:

```
_row_to_dict(row)   ->  dict          pure function, no side effects
row_to_image(row)   ->  ImageOut      composed: _row_to_dict -> ImageOut(**...)
```

---

## Request Lifecycle

### Example: POST /images/ (upload a new image)

```
1.  Browser sends multipart/form-data with file + content

2.  Uvicorn receives the request and passes it to FastAPI

3.  Rate limiter (slowapi) checks the client IP
    - If over 200 req/min: returns 429 immediately
    - Otherwise: continues

4.  FastAPI validates Form fields via Pydantic
    - content empty or > 500 chars: returns 422 immediately
    - Otherwise: continues

5.  Router (routers/images.py)
    - Extracts: file (UploadFile), content (str), db (Connection)
    - Calls: image_service.create_image(file, content, db)

6.  Service (image_service.py) — create_image pipeline
    a. _validate_mime(file)
       - content_type does not start with "image/": raises InvalidFileError
    b. _validate_extension(file.filename)
       - extension not in allowlist: raises InvalidFileError
    c. raw = await file.read()
    d. _validate_size(raw)
       - len(raw) > 10MB: raises FileTooLargeError
    e. _upload_to_imagekit(raw, filename)
       - ImageKit SDK call fails: raises StorageError
       - Success: returns result with .url and .file_id
    f. image_repo.insert(db, filename, content, url, file_id)
       - Executes INSERT, commits, fetches the new row
       - Returns ImageOut

7.  Router receives ImageOut, returns HTTP 201 with JSON body

8.  If any typed exception was raised in steps 6a-6f:
    - Global handler in app.py catches it
    - Returns the appropriate HTTP error response (400 / 413 / 502)
    - No exception propagates to the client as a 500
```

---

## Data Flow

### Write path (upload)

```
Browser
  |  multipart/form-data (file bytes + caption string)
  v
Router
  |  UploadFile, str
  v
Service
  |  validates, reads bytes, calls ImageKit
  |
  |-- ImageKit.io  <-- raw bytes
  |                --> { url, file_id }
  |
  |  (filename, caption, url, file_id)
  v
Repository
  |  INSERT INTO images ...
  v
SQLite (images.db)
  |  returns new row
  v
Repository  ->  ImageOut
  v
Service     ->  ImageOut
  v
Router      ->  HTTP 201 { id, filename, content, url, file_id }
  v
Browser
```

### Read path (list feed)

```
Browser
  |  GET /images/?limit=20&offset=0
  v
Router
  |  limit: int, offset: int
  v
Service
  |  passes through to repository
  v
Repository
  |  SELECT * FROM images ORDER BY id DESC LIMIT ? OFFSET ?
  v
SQLite
  |  returns rows
  v
Repository
  |  [row_to_image(r) for r in rows]   <- list comprehension pipeline
  v
Service  ->  list[ImageOut]
  v
Router   ->  HTTP 200 [ {...}, {...}, ... ]
  v
Browser  ->  renders feed cards
```

### Delete path

```
Browser
  |  DELETE /images/{id}
  v
Router
  v
Service
  |  1. image_repo.get_file_id(db, id)
  |     - None: raises ImageNotFoundError -> 404
  |  2. _delete_from_imagekit(file_id)
  |     - fails: raises StorageError -> 502
  |  3. image_repo.delete(db, id)
  v
SQLite  (row removed)
  v
Router  ->  HTTP 204 No Content
  v
Browser ->  removes card from DOM
```

---

## Component Responsibilities

| File | Knows About | Does NOT Know About |
|---|---|---|
| `main.py` | Uvicorn config | Everything else |
| `app.py` | FastAPI setup, logging, rate limiting, error formatting | SQL, ImageKit, business rules |
| `routers/images.py` | HTTP methods, paths, query params, status codes | SQL, ImageKit, business rules |
| `services/image_service.py` | Validation rules, ImageKit SDK, exception types | HTTP status codes, raw SQL |
| `repositories/image_repo.py` | SQL syntax, aiosqlite, table schema | HTTP, ImageKit, business rules |
| `schemas.py` | Pydantic field constraints | Everything else |
| `exceptions.py` | Exception type definitions | Everything else |
| `db.py` | aiosqlite connection lifecycle | Business logic, HTTP |
| `templates/index.html` | DOM, fetch API, pagination state | Python, SQL |

---

## Dependency Graph

Arrows show "imports / depends on":

```
main.py
  `-> app.app

app.app
  `-> app.db              (init_db)
  `-> app.exceptions      (exception types for handlers)
  `-> app.routers.images  (router)

app.routers.images
  `-> app.db              (get_db dependency)
  `-> app.schemas         (ImageOut response model)
  `-> app.services.image_service

app.services.image_service
  `-> app.exceptions      (raises typed errors)
  `-> app.repositories.image_repo
  `-> app.schemas         (ImageOut)
  `-> imagekitio          (external SDK)

app.repositories.image_repo
  `-> app.schemas         (ImageOut)
  `-> aiosqlite           (DB driver)

app.schemas
  `-> pydantic            (BaseModel, Field)

app.exceptions
  (no internal imports)

app.db
  `-> aiosqlite
```

Key property: the dependency arrows only point downward.
Router -> Service -> Repository. No layer imports from the layer above it.
This is what makes each layer independently testable.

---

## Error Handling Strategy

Errors flow upward through typed exceptions. The global handler in `app.py` is the
single place that converts them to HTTP responses.

```
Repository  ->  propagates DB exceptions upward (no catching)
    |
Service     ->  catches Exception from ImageKit, re-raises as StorageError
            ->  raises InvalidFileError, FileTooLargeError, ImageNotFoundError
    |
Router      ->  does not catch anything (global handlers cover all cases)
    |
app.py      ->  @exception_handler(ImageNotFoundError)  -> 404
            ->  @exception_handler(InvalidFileError)    -> 400
            ->  @exception_handler(FileTooLargeError)   -> 413
            ->  @exception_handler(StorageError)        -> 502
            ->  @exception_handler(RateLimitExceeded)   -> 429
```

All error responses share the same JSON shape:

```json
{ "detail": "Human-readable message here" }
```

Internal error details (stack traces, ImageKit error codes) are written to the
server log via `logger.error(..., exc_info=True)` and never sent to the client.

---

## External Integrations

### ImageKit.io

- SDK: `imagekitio` v5
- Initialised once at module load in `image_service.py`
- Two operations used: `files.upload()` and `files.delete()`
- Both are wrapped in try/except and isolated in their own functions
  (`_upload_to_imagekit`, `_delete_from_imagekit`) so they can be mocked in tests
- Credentials loaded from `.env` via `python-dotenv`

### SQLite via aiosqlite

- One connection opened per request via the `get_db()` FastAPI dependency
- `try/finally` guarantees the connection is always closed
- All queries use `?` parameterized placeholders (SQL injection prevention)
- `row_factory = aiosqlite.Row` enables column-name access on result rows

---

## Security Architecture

| Layer | Measure | Where |
|---|---|---|
| Network | Rate limiting 200 req/min per IP | `app.py` — slowapi |
| HTTP | Form field length enforced (1–500 chars) | `routers/images.py` — FastAPI Form |
| Service | MIME type validation (must start with `image/`) | `image_service._validate_mime` |
| Service | File extension allowlist (.jpg .jpeg .png .gif .webp .avif) | `image_service._validate_extension` |
| Service | File size limit 10 MB server-side | `image_service._validate_size` |
| Database | Parameterized queries on all SQL | `repositories/image_repo.py` |
| Frontend | HTML entity escaping before DOM insertion | `index.html` — `sanitize()` |
| Frontend | Content set via `textContent`, never `innerHTML` | `index.html` — `saveEdit()` |
| Frontend | No inline `onclick` — event delegation with `data-action` | `index.html` |
| Frontend | Client-side MIME and size pre-check | `index.html` — `showPreview()`, `submitPost()` |
| Config | All secrets in `.env`, never hardcoded | `.env` + `python-dotenv` |

---

## Design Decisions and Trade-offs

### SQLite instead of PostgreSQL

SQLite is a single file with no server process, which makes it ideal for a learning
project or a low-traffic deployment. The trade-off is that SQLite does not support
concurrent writes — only one write can happen at a time. For a production system
with multiple users, PostgreSQL with `asyncpg` would be the correct choice.
Because all SQL is isolated in `image_repo.py`, this migration only requires
rewriting that one file.

### One DB connection per request

`get_db()` opens and closes a connection for every request. This is simple and
correct for SQLite. For PostgreSQL, you would replace this with a connection pool
(e.g. `asyncpg.create_pool`) and yield a connection from the pool instead.

### ImageKit before DB on delete

In `delete_image`, the ImageKit file is deleted before the database row is removed.
If the database delete fails after a successful ImageKit delete, the database record
becomes an orphan pointing to a file that no longer exists. This is an acceptable
trade-off for SQLite. For a production system, the correct approach is to use a
background job or a compensating transaction.

### No authentication

All CRUD operations are currently open — any user can edit or delete any post.
Adding JWT authentication would require a `users` table, a `POST /auth/login`
endpoint, and a `get_current_user` FastAPI dependency injected into the protected
routes. The layer structure makes this straightforward to add without touching
existing business logic.

### Synchronous ImageKit SDK calls inside async handlers

The `imagekitio` v5 SDK is synchronous. Calling it directly inside an async
function blocks the event loop for the duration of the HTTP request to ImageKit.
For a low-traffic application this is acceptable. For higher throughput, the
correct fix is to wrap the call with `asyncio.to_thread()`:

```python
result = await asyncio.to_thread(
    _imagekit.files.upload,
    file=raw,
    file_name=filename,
    use_unique_file_name=True,
)
```
