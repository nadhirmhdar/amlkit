"""Trade licence OCR endpoint for legal-person onboarding (web route).

Mirrors test_new_features_e2e.py's TestIdentityVerificationE2E for the
passport route: same client fixture, same "garbage bytes still degrades
cleanly" and "CSRF is enforced" contract.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_api import _csrf, client  # noqa: F401,E402


def test_scan_trade_licence_returns_trade_licence_shaped_fields(client) -> None:  # noqa: F811
    r = client.post(
        "/customers/scan-trade-licence",
        files={"licence_file": ("licence.jpg", io.BytesIO(b"not a real image"), "image/jpeg")},
        data={"csrf_token": _csrf(client)},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["id_type"] == "trade_licence"
    for field in ("full_name", "id_number", "legal_type", "issue_date", "expiry_date", "issuing_authority"):
        assert field in data


def test_scan_trade_licence_requires_login(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "anon.db"))
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    c = TestClient(app)
    r = c.post(
        "/customers/scan-trade-licence",
        files={"licence_file": ("licence.jpg", io.BytesIO(b"x"), "image/jpeg")},
    )
    assert r.status_code == 401


def test_scan_trade_licence_rejects_missing_csrf_token(client) -> None:  # noqa: F811
    r = client.post(
        "/customers/scan-trade-licence",
        files={"licence_file": ("licence.jpg", io.BytesIO(b"not a real image"), "image/jpeg")},
    )
    assert r.status_code == 403


def test_scan_trade_licence_extracts_real_fields_from_ocr_text(client, monkeypatch) -> None:  # noqa: F811
    """The route itself is a thin wrapper -- the field-extraction logic is
    already covered against real OCR-shaped text in test_ocr.py. Here we only
    prove the route is wired to the trade-licence extractor (not the passport
    one) and returns its fields untouched."""
    from amlkit.cases import ocr

    monkeypatch.setattr(
        ocr, "extract_trade_licence_data",
        lambda f: {"id_type": "trade_licence", "full_name": "FALCON RIDGE TRADING FZE",
                   "id_number": "749278", "legal_type": "LLC", "issue_date": None,
                   "expiry_date": None, "issuing_authority": None,
                   "expiry_check": {"expired": None}, "field_confidence": {}},
    )
    r = client.post(
        "/customers/scan-trade-licence",
        files={"licence_file": ("licence.jpg", io.BytesIO(b"x"), "image/jpeg")},
        data={"csrf_token": _csrf(client)},
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "FALCON RIDGE TRADING FZE"
    assert r.json()["id_number"] == "749278"
