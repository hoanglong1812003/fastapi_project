"""
exceptions.py — Centralised custom exception types.

WHY: Routes and services raise typed exceptions instead of raw HTTPException.
     A single global handler in app.py converts them to HTTP responses.
     Changing the error format means editing ONE place, not every route.
"""


class ImageNotFoundError(Exception):
    """Raised when an image ID does not exist in the database."""
    def __init__(self, image_id: int) -> None:
        self.image_id = image_id
        super().__init__(f"Image {image_id} not found")


class StorageError(Exception):
    """Raised when ImageKit upload or delete fails."""
    pass


class InvalidFileError(Exception):
    """Raised when the uploaded file fails MIME or extension validation."""
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FileTooLargeError(Exception):
    """Raised when the uploaded file exceeds the size limit."""
    def __init__(self, max_mb: int) -> None:
        self.max_mb = max_mb
        super().__init__(f"File exceeds {max_mb}MB limit")
