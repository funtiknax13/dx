import contextlib
import io
import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps

from app.core.config import settings

THUMBNAIL_SIZE = (480, 480)
_PIL_FORMAT_BY_EXT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


class FileTooLargeError(ValueError):
    pass


class InvalidFileTypeError(ValueError):
    pass


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    content = await upload.read()
    if len(content) > max_bytes:
        raise FileTooLargeError(f"File exceeds maximum size of {max_bytes} bytes")
    return content


def _ext(filename: str | None) -> str:
    return Path(filename or "").suffix.lower()


def _save_bytes(content: bytes, subdir: str, ext: str) -> str:
    """Persist bytes under MEDIA_ROOT/subdir and return the public media path."""
    dest_dir = Path(settings.media_root) / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    dest = dest_dir / fname
    with open(dest, "wb") as f:
        f.write(content)
    return f"{settings.media_url}/{subdir}/{fname}"


async def save_image(upload: UploadFile, subdir: str) -> str:
    ext = _ext(upload.filename)
    if ext not in settings.allowed_image_extensions:
        raise InvalidFileTypeError("Image must be jpg, jpeg, png or webp")
    content = await _read_limited(upload, settings.max_image_size_bytes)
    return _save_bytes(content, subdir, ext)


def _make_thumbnail(content: bytes, ext: str) -> bytes:
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(content)))
    fmt = _PIL_FORMAT_BY_EXT[ext]
    if fmt == "JPEG" and image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail(THUMBNAIL_SIZE)
    buf = io.BytesIO()
    image.save(buf, format=fmt, quality=82)
    return buf.getvalue()


async def save_image_with_thumbnail(upload: UploadFile, subdir: str) -> tuple[str, str]:
    """Save the original image plus a resized copy under `{subdir}/thumbs`.

    Returns (image_path, thumbnail_path).
    """
    ext = _ext(upload.filename)
    if ext not in settings.allowed_image_extensions:
        raise InvalidFileTypeError("Image must be jpg, jpeg, png or webp")
    content = await _read_limited(upload, settings.max_image_size_bytes)
    path = _save_bytes(content, subdir, ext)
    thumb_content = _make_thumbnail(content, ext)
    thumb_path = _save_bytes(thumb_content, f"{subdir}/thumbs", ext)
    return path, thumb_path


async def save_track_file(upload: UploadFile, subdir: str) -> tuple[str, bytes, str]:
    """Save a GPX/FIT file. Returns (media_path, raw_bytes, extension)."""
    ext = _ext(upload.filename)
    if ext not in settings.allowed_track_extensions:
        raise InvalidFileTypeError("Track file must be .gpx or .fit")
    content = await _read_limited(upload, settings.max_track_file_size_bytes)
    path = _save_bytes(content, subdir, ext)
    return path, content, ext


def save_track_bytes(content: bytes, ext: str, subdir: str) -> str:
    """Same validation/storage as save_track_file, for content that didn't
    arrive as an UploadFile (e.g. downloaded from a URL) — see safe_fetch."""
    if ext not in settings.allowed_track_extensions:
        raise InvalidFileTypeError("Track file must be .gpx or .fit")
    if len(content) > settings.max_track_file_size_bytes:
        raise FileTooLargeError(
            f"File exceeds maximum size of {settings.max_track_file_size_bytes} bytes"
        )
    return _save_bytes(content, subdir, ext)


def media_path_to_fs(media_path: str) -> Path:
    rel = media_path.removeprefix(settings.media_url).lstrip("/")
    return Path(settings.media_root) / rel


def delete_media(media_path: str | None) -> None:
    if not media_path:
        return
    fs = media_path_to_fs(media_path)
    with contextlib.suppress(FileNotFoundError):
        os.remove(fs)
