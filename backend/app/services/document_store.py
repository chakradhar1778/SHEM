"""
SHEM Backend — Bill document storage (images / PDFs kept for viewing; never parsed, no OCR)

Documents are stored in the database (bill_document_chunks), so they live in
Turso and survive restarts on hosts with an ephemeral disk (Render free tier).
Documents uploaded by older versions under UPLOADS_DIR/bills/ are still served
and cleaned up. The type is decided from the file's own bytes (magic number)
and must match the declared Content-Type, so a renamed script can't be stored
as a "PDF".
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import BillDocumentChunk, ElectricityBill

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


DB_MARKER = "db"                 # ElectricityBill.document_path value for documents stored in the DB
CHUNK_SIZE = 256 * 1024          # bytes per row; keeps each libSQL/Turso request small


def save(db: Session, bill_id: str, data: bytes, previous: Optional[str] = None) -> Tuple[str, int]:
    """
    Store the document in bill_document_chunks (replacing any earlier one) and
    remove a legacy on-disk file. Returns (document_path marker, size). The
    caller commits, so bytes and bill metadata land in the same transaction.
    """
    _delete_chunks(db, bill_id)
    for seq, start in enumerate(range(0, len(data), CHUNK_SIZE)):
        db.add(BillDocumentChunk(bill_id=bill_id, seq=seq, data=data[start:start + CHUNK_SIZE]))
    delete_legacy_file(previous)
    return DB_MARKER, len(data)


def load(db: Session, bill: ElectricityBill) -> Optional[bytes]:
    """The document bytes, from the DB or (older uploads) from UPLOADS_DIR; None if gone."""
    if not bill.document_path:
        return None
    if bill.document_path == DB_MARKER:
        rows = db.execute(
            select(BillDocumentChunk.data)
            .where(BillDocumentChunk.bill_id == bill.id)
            .order_by(BillDocumentChunk.seq)
        ).scalars().all()
        return b"".join(bytes(r) for r in rows) if rows else None
    path = resolve(bill.document_path)
    return path.read_bytes() if path is not None else None


def delete(db: Session, bill_id: str, document_path: Optional[str]) -> None:
    """Remove a bill's document wherever it lives (caller commits)."""
    _delete_chunks(db, bill_id)
    delete_legacy_file(document_path)


def _delete_chunks(db: Session, bill_id: str) -> None:
    db.execute(sa_delete(BillDocumentChunk).where(BillDocumentChunk.bill_id == bill_id))


# ── Legacy on-disk documents (uploaded before DB storage) ─────────────────────

def root() -> Path:
    return Path(settings.uploads_dir).resolve() / "bills"


def resolve(rel_path: str) -> Optional[Path]:
    """Absolute path inside UPLOADS_DIR, or None if missing / outside it."""
    base = Path(settings.uploads_dir).resolve()
    p = (base / rel_path).resolve()
    if not p.is_relative_to(base) or not p.is_file():
        return None
    return p


def delete_legacy_file(rel_path: Optional[str]) -> None:
    if not rel_path or rel_path == DB_MARKER:
        return
    p = resolve(rel_path)
    if p is not None:
        try:
            p.unlink()
        except OSError:
            pass
