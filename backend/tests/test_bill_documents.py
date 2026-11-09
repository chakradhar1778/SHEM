"""Bill documents: stored for viewing (no OCR); type verified from the bytes; size limit; cleanup."""

from __future__ import annotations

import shutil

import pytest

from app.services import document_store
from conftest import AUTH


@pytest.fixture(autouse=True)
def empty_uploads():
    shutil.rmtree(document_store.root(), ignore_errors=True)
    yield

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
    assert client.get(f"/api/bills/{bid}/document").status_code == 401          # API key required

    # Replacing with a PDF removes the old PNG file
    assert upload(client, bid, PDF, "application/pdf").json()["documentContentType"] == "application/pdf"
    assert list(document_store.root().glob("*")) == [document_store.root() / f"{bid}.pdf"]

    d = client.delete(f"/api/bills/{bid}/document", headers=AUTH).json()
    assert d["hasDocument"] is False and not list(document_store.root().glob("*"))
    assert client.get(f"/api/bills/{bid}/document", headers=AUTH).status_code == 404


def test_rejects_wrong_or_disguised_files(client):
    bid = bill(client)
    assert upload(client, bid, b"<script>alert(1)</script>", "application/pdf").status_code == 415
    assert upload(client, bid, PDF, "image/png").status_code == 415                  # declared ≠ actual
    assert upload(client, bid, b"", "image/png").status_code == 400
    assert upload(client, bid, b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 1), "image/png").status_code == 413
    assert upload(client, "missing", PNG, "image/png").status_code == 404
    assert not document_store.root().exists() or not list(document_store.root().glob("*"))


def test_deleting_bill_removes_its_document(client):
    bid = bill(client)
    upload(client, bid, PDF, "application/pdf")
    assert list(document_store.root().glob("*"))
    assert client.delete(f"/api/bills/{bid}", headers=AUTH).status_code == 204
    assert not list(document_store.root().glob("*"))
