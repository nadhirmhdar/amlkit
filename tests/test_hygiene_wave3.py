"""WP-21 hygiene follow-ups (policy blob names, evidence title, PDF page bomb, seed_org)."""

from __future__ import annotations

import io
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import real_image_bytes, register_org


@pytest.fixture()
def web(tmp_path, monkeypatch):
    """App on a throwaway DB with one registered, logged-in MLRO."""
    from amlkit.db import connect
    from conftest import seed_fresh_dataset

    db_file = tmp_path / "hyg.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    c0 = connect(db_file)
    seed_fresh_dataset(c0)
    c0.close()
    from amlkit.api.app import app

    c = TestClient(app)
    register_org(c, "Hyg Firm", "alice", "alice@hygfirm.ae")
    return c


# ---- 5: seed_org fixture ------------------------------------------------

def test_seed_org_fixture_gives_org_mlro_and_officer(seed_org, conn) -> None:
    from amlkit.auth import verify_password

    rows = conn.execute(
        "SELECT role, password_hash, is_active, email_verified_at FROM operators WHERE org_id=? ORDER BY role",
        (seed_org["org_id"],),
    ).fetchall()
    assert [r["role"] for r in rows] == ["mlro", "officer"]
    for r in rows:
        assert r["is_active"] == 1 and r["email_verified_at"]
        assert verify_password(seed_org["password"], r["password_hash"])


# ---- 1: policy blobs keep distinct names --------------------------------

def test_policy_versions_with_same_filename_keep_both_blobs(seed_org, conn) -> None:
    from amlkit.cases.manager import upload_policy
    from amlkit.storage import download_policy

    org = seed_org["org_id"]
    p1, v1 = upload_policy(conn, org_id=org, title="AML Policy", category="AML_Policy",
                           filename="policy.pdf", file_content=b"%PDF-1 one", uploaded_by="Seed MLRO")
    p2, v2 = upload_policy(conn, org_id=org, title="AML Policy", category="AML_Policy",
                           filename="policy.pdf", file_content=b"%PDF-1 two", uploaded_by="Seed MLRO")
    assert (v1, v2) == (1, 2)
    rows = {r["id"]: r for r in conn.execute("SELECT id, filename, stored_path FROM policy_documents")}
    assert rows[p1]["stored_path"] != rows[p2]["stored_path"]
    assert rows[p1]["filename"] == rows[p2]["filename"] == "policy.pdf"
    assert download_policy(rows[p1]["stored_path"]) == b"%PDF-1 one"
    assert download_policy(rows[p2]["stored_path"]) == b"%PDF-1 two"
    for r in rows.values():
        os.remove(r["stored_path"])


# ---- 2: evidence template title ----------------------------------------

def test_evidence_pack_title_has_no_customer_name_but_body_does(web) -> None:
    c = web
    csrf = c.cookies.get("amlkit_csrf")
    c.post("/customers", data={"reference": "C-T", "full_name": "Zephyr Holdings FZE",
                               "customer_type": "legal", "csrf_token": csrf}, follow_redirects=True)
    path = os.environ["AMLKIT_DB"]
    cid = sqlite3.connect(path).execute("SELECT id FROM customers ORDER BY id DESC LIMIT 1").fetchone()[0]
    html = c.get(f"/customers/{cid}/evidence").text
    title = html.split("<title>", 1)[1].split("</title>", 1)[0]
    assert title.strip() == "Evidence pack — groAML"
    assert "Zephyr" not in title
    assert "Zephyr Holdings FZE" in html


# ---- 4: PDF page bomb ---------------------------------------------------

def _pdf(width_pt: float, height_pt: float, pages: int = 1, sizes=None) -> bytes:
    """A tiny hand-built PDF whose pages declare the given MediaBox."""
    sizes = sizes or [(width_pt, height_pt)] * pages
    objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + i} 0 R" for i in range(len(sizes)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(sizes)} >>")
    for w, h in sizes:
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w} {h}] >>")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def test_validate_upload_refuses_pdf_page_bomb() -> None:
    from amlkit.validation import PDF, UploadTooLarge, validate_upload

    with pytest.raises(UploadTooLarge) as ei:
        validate_upload(_pdf(3000, 3000), allowed_mimes={PDF}, check_pdf_pages=True)
    assert "megapixels" in str(ei.value) and ei.value.status_code == 413


def test_validate_upload_accepts_a4_and_checks_only_first_five_pages() -> None:
    from amlkit.validation import PDF, UploadTooLarge, validate_upload

    assert validate_upload(_pdf(595, 842), allowed_mimes={PDF}, check_pdf_pages=True) == PDF
    # A bomb on page 6 is never rendered (only the first 5 pages are inspected/used).
    sizes = [(595, 842)] * 5 + [(3000, 3000)]
    assert validate_upload(_pdf(0, 0, sizes=sizes), allowed_mimes={PDF}, check_pdf_pages=True) == PDF
    # ...but one on page 5 is refused.
    sizes = [(595, 842)] * 4 + [(3000, 3000)]
    with pytest.raises(UploadTooLarge):
        validate_upload(_pdf(0, 0, sizes=sizes), allowed_mimes={PDF}, check_pdf_pages=True)


def test_pdf_pixel_cap_follows_env(monkeypatch) -> None:
    from amlkit.validation import PDF, UploadTooLarge, validate_upload

    monkeypatch.setenv("AMLKIT_MAX_IMAGE_PIXELS", "1000000")
    with pytest.raises(UploadTooLarge):
        validate_upload(_pdf(595, 842), allowed_mimes={PDF}, check_pdf_pages=True)


def test_scan_route_returns_413_for_pdf_page_bomb(web) -> None:
    c = web
    csrf = c.cookies.get("amlkit_csrf")
    r = c.post("/customers/scan-passport", data={"csrf_token": csrf},
               files={"passport_file": ("p.pdf", _pdf(3000, 3000), "application/pdf")})
    assert r.status_code == 413
    ok = c.post("/customers/scan-passport", data={"csrf_token": csrf},
                files={"passport_file": ("p.png", real_image_bytes("PNG"), "image/png")})
    assert ok.status_code != 413


def test_ocr_renderer_refuses_oversized_page_before_rendering() -> None:
    from amlkit.cases import ocr

    with pytest.raises(ValueError):
        ocr._pdf_first_page_to_image_bytes(_pdf(3000, 3000))
