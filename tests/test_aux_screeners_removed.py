"""The unlinked auxiliary Google screeners (kg-screen, gdelt-bq) are gone
(L-91..L-94, owner decision 7a: delete)."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.test_api import _csrf, _db, client  # noqa: F401  (shared fixture/helpers)

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("suffix", ["kg-screen", "gdelt-bq"])
def test_routes_are_404(client, suffix) -> None:
    client.post("/customers", data={
        "reference": "AUX-1", "full_name": "Ahmed Al Mansoori",
        "customer_type": "natural", "csrf_token": _csrf(client),
    }, follow_redirects=True)
    conn = _db()
    cid = conn.execute("SELECT id FROM customers WHERE reference='AUX-1'").fetchone()["id"]
    conn.close()
    assert client.get(f"/customers/{cid}/{suffix}").status_code == 404


@pytest.mark.parametrize("mod", ["knowledge_graph", "gdelt_bq"])
def test_modules_not_importable(mod) -> None:
    with pytest.raises(ImportError):
        importlib.import_module(f"amlkit.screening.{mod}")


def test_no_template_or_js_references() -> None:
    hits = []
    for d in ("amlkit",):
        for f in (ROOT / d).rglob("*"):
            if f.suffix in {".html", ".js", ".jinja", ".j2"} and f.is_file():
                text = f.read_text(errors="ignore")
                if "kg-screen" in text or "gdelt-bq" in text:
                    hits.append(str(f))
    assert hits == []
