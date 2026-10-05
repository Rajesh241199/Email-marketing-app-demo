"""Object storage abstraction.

Development/test implementation writes to local disk under ``settings.upload_dir``.
A production implementation (S3) would implement the same two methods and be swapped in
without touching any router.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.upload_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, *, filename: str, content: bytes) -> str:
        ext = Path(filename).suffix
        key = f"{uuid.uuid4()}{ext}"
        (self.base_dir / key).write_bytes(content)
        return key

    def read(self, key: str) -> bytes:
        return (self.base_dir / key).read_bytes()

    def url_for(self, key: str) -> str:
        return f"/media/{key}"

    def delete(self, key: str) -> None:
        path = self.base_dir / key
        path.unlink(missing_ok=True)


storage = LocalStorage()
