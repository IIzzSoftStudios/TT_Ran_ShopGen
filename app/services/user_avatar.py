"""Avatar file storage and validation."""

from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path

from flask import current_app
from PIL import Image

MAX_UPLOAD_BYTES = 512 * 1024
AVATAR_SIZE = (256, 256)
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def avatar_dir() -> Path:
    root = Path(current_app.root_path).parent
    path = root / "uploads" / "avatars"
    path.mkdir(parents=True, exist_ok=True)
    return path


def avatar_path_for_user(user_id: int) -> Path:
    return avatar_dir() / f"{user_id}.webp"


def save_avatar(user_id: int, file_storage) -> None:
    """Validate, resize, and write WebP for ``user_id``."""
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    if size > MAX_UPLOAD_BYTES:
        raise ValueError("File exceeds max 512 KB allowed size.")
    file_storage.stream.seek(0)

    Image.MAX_IMAGE_PIXELS = 8_000_000
    img = Image.open(file_storage.stream)
    if img.format not in ALLOWED_FORMATS:
        raise ValueError("Unsupported image format.")
    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.thumbnail(AVATAR_SIZE, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)
    target = avatar_path_for_user(user_id)
    target.write_bytes(out.getvalue())


def delete_avatar_file(user_id: int) -> None:
    path = avatar_path_for_user(user_id)
    if path.exists():
        path.unlink()


def touch_avatar_timestamp(user) -> datetime:
    ts = datetime.utcnow()
    user.avatar_updated_at = ts
    return ts
