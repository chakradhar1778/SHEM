"""
SHEM Backend — Bill document storage (images / PDFs kept for viewing; never parsed, no OCR)

Files live under UPLOADS_DIR/bills/<bill-id>.<ext>. The type is decided from the
file's own bytes (magic number) and must match the declared Content-Type, so a
renamed script can't be stored as a "PDF". Names on disk come from the bill id
(sanitised), never from user input.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from app.config import get_settings

settings = get_settings()

ALLOWED = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


class DocumentError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def sniff(data: bytes) -> Optional[str]:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def root() -> Path:
    return Path(settings.uploads_dir).resolve() / "bills"


def _safe_stem(bill_id: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]", "", bill_id)[:64]
    return stem if stem == bill_id and stem else "bill-" + hashlib.sha256(bill_id.encode()).hexdigest()[:24]


def validate(data: bytes, declared: str) -> str:
    """Returns the verified content type or raises DocumentError."""
    if not data:
        raise DocumentError(400, "Empty file.")
    limit = int(settings.max_bill_document_mb * 1024 * 1024)
    if len(data) > limit:
        raise DocumentError(413, f"File too large (max {settings.max_bill_document_mb:g} MB).")
    declared = (declared or "").split(";")[0].strip().lower()
    if declared == "image/jpg":
        declared = "image/jpeg"
    actual = sniff(data)
    if actual is None:
        raise DocumentError(415, "Only JPG, PNG, WebP or PDF files can be attached.")
    if declared and declared != "application/octet-stream" and declared != actual:
        raise DocumentError(415, f"The file content is {actual}, not {declared}.")
    return actual


def save(bill_id: str, data: bytes, content_type: str, previous: Optional[str] = None) -> Tuple[str, int]:
    """Write atomically; returns (relative path, size). Removes a previous file with another extension."""
    folder = root()
    folder.mkdir(parents=True, exist_ok=True)
    name = _safe_stem(bill_id) + ALLOWED[content_type]
    target = folder / name
    tmp = folder / (name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, target)
    if previous and previous != f"bills/{name}":
        delete(previous)
    return f"bills/{name}", len(data)


def resolve(rel_path: str) -> Optional[Path]:
    """Absolute path inside UPLOADS_DIR, or None if missing / outside it."""
    base = Path(settings.uploads_dir).resolve()
    p = (base / rel_path).resolve()
    if not p.is_relative_to(base) or not p.is_file():
        return None
    return p


def delete(rel_path: Optional[str]) -> None:
    if not rel_path:
        return
    p = resolve(rel_path)
    if p is not None:
        try:
            p.unlink()
        except OSError:
            pass
