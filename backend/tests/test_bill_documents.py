"""Bill documents: stored in the DB for viewing (no OCR); type verified from the bytes; size limit; cleanup."""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.db_models import BillDocumentChunk, ElectricityBill
from app.services import document_store
from conftest import AUTH


@pytest.fixture(autouse=True)
def empty_uploads():
    shutil.rmtree(document_store.root(), ignore_errors=True)
    yield


def chunk_count(bid):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(BillDocumentChunk)
                         .where(BillDocumentChunk.bill_id == bid))


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%fake test pdf\n"


def bill(client):
    r = client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026,
                                                      "unitsConsumedKWh": 100, "billAmountINR": 800})
    return r.json()["id"]


def upload(client, bid, data, ctype, name=None):
    q = f"?filename={name}" if name else ""
    return client.put(f"/api/bills/{bid}/document{q}", headers={**AUTH, "Content-Type": ctype}, content=data)


def test_upload_view_and_delete(client):
    bid = bill(client)
    assert client.get("/api/bills", headers=AUTH).json()[0]["hasDocument"] is False
    r = upload(client, bid, PNG, "image/png", "march bill.png")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["hasDocument"] and b["documentContentType"] == "image/png" and b["documentSize"] == len(PNG)
    assert b["documentFilename"] == "march bill.png"

    got = client.get(f"/api/bills/{bid}/document", headers=AUTH)
    assert got.status_code == 200 and got.content == PNG
    assert got.headers["content-type"] == "image/png" and got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-disposition"].startswith("inline")
    assert "march%20bill.png" in got.headers["content-disposition"]
    assert client.get(f"/api/bills/{bid}/document").status_code == 401          # API key required

    # Stored in the database (survives an ephemeral disk), nothing written to UPLOADS_DIR
    assert chunk_count(bid) == 1 and not document_store.root().exists()

    # Replacing with a PDF replaces the stored bytes
    assert upload(client, bid, PDF, "application/pdf").json()["documentContentType"] == "application/pdf"
    assert client.get(f"/api/bills/{bid}/document", headers=AUTH).content == PDF
    assert chunk_count(bid) == 1

    d = client.delete(f"/api/bills/{bid}/document", headers=AUTH).json()
    assert d["hasDocument"] is False and chunk_count(bid) == 0
    assert client.get(f"/api/bills/{bid}/document", headers=AUTH).status_code == 404


def test_rejects_wrong_or_disguised_files(client):
    bid = bill(client)
    assert upload(client, bid, b"<script>alert(1)</script>", "application/pdf").status_code == 415
    assert upload(client, bid, PDF, "image/png").status_code == 415                  # declared ≠ actual
    assert upload(client, bid, b"", "image/png").status_code == 400
    assert upload(client, bid, b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 1), "image/png").status_code == 413
    assert upload(client, "missing", PNG, "image/png").status_code == 404
    assert chunk_count(bid) == 0


def test_deleting_bill_removes_its_document(client):
    bid = bill(client)
    upload(client, bid, PDF, "application/pdf")
    assert chunk_count(bid) == 1
    assert client.delete(f"/api/bills/{bid}", headers=AUTH).status_code == 204
    assert chunk_count(bid) == 0


def test_large_document_is_chunked_and_reassembled(client, monkeypatch):
    monkeypatch.setattr(document_store, "CHUNK_SIZE", 1000)
    bid = bill(client)
    data = PDF + bytes(range(256)) * 20                     # ~5.1 KB -> 6 chunks
    assert upload(client, bid, data, "application/pdf").status_code == 200
    assert chunk_count(bid) == 6
    assert client.get(f"/api/bills/{bid}/document", headers=AUTH).content == data


def test_legacy_disk_document_still_served_then_moved_to_db(client):
    """Documents uploaded by older versions live in UPLOADS_DIR/bills/ and keep working."""
    bid = bill(client)
    document_store.root().mkdir(parents=True, exist_ok=True)
    (document_store.root() / f"{bid}.png").write_bytes(PNG)
    with SessionLocal() as db:
        b = db.get(ElectricityBill, bid)
        b.document_path, b.document_content_type, b.document_size = f"bills/{bid}.png", "image/png", len(PNG)
        db.commit()

    got = client.get(f"/api/bills/{bid}/document", headers=AUTH)
    assert got.status_code == 200 and got.content == PNG

    # Re-uploading stores it in the DB and removes the old file
    upload(client, bid, PDF, "application/pdf")
    assert chunk_count(bid) == 1 and not list(document_store.root().glob("*"))
    assert client.get(f"/api/bills/{bid}/document", headers=AUTH).content == PDF


def test_missing_legacy_file_is_404(client):
    bid = bill(client)
    with SessionLocal() as db:
        db.get(ElectricityBill, bid).document_path = f"bills/{bid}.png"
        db.commit()
    assert client.get(f"/api/bills/{bid}/document", headers=AUTH).status_code == 404
