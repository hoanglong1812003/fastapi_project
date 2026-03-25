"""
KIẾN THỨC ÁP DỤNG:
- [Package Management - uv] : pydantic (bundled với fastapi) quản lý qua uv
- [Functional Programming]  : ImageOut là immutable data class, dùng để transform dict → typed object
"""

from pydantic import BaseModel

class ImageOut(BaseModel):
    id:       int
    filename: str
    content:  str
    url:      str
    file_id:  str
