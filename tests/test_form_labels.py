"""Form controls on the decision and screening pages carry accessible names.

Audit finding: the alert disposition form (decision, reason, narrative) and
the Screen-a-name fields had ``<label>`` tags with no ``for``, so screen
readers announced bare "combobox"/"edit" controls on the sanctions decision
form. Every control below must be reachable by a label or aria-label.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_api import client  # noqa: E402,F401

TEMPLATES = Path(__file__).resolve().parent.parent / "amlkit" / "web" / "templates"
_CONTROL = re.compile(r"<(input|select|textarea)\b([^>]*)>", re.S)


def _unnamed(html: str) -> list[str]:
    labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))
    bad = []
    for m in _CONTROL.finditer(html):
        attrs = m.group(2)
        if re.search(r'type="(hidden|checkbox|radio|submit)"', attrs):
            continue
        ident = re.search(r'\bid="([^"]+)"', attrs)
        if "aria-label" in attrs or (ident and ident.group(1) in labelled):
            continue
        bad.append(m.group(0)[:80])
    return bad


def test_screen_page_fields_are_labelled(client) -> None:
    r = client.get("/screen")
    assert r.status_code == 200
    assert _unnamed(r.text) == []


def test_customers_search_is_labelled(client) -> None:
    r = client.get("/customers")
    assert r.status_code == 200
    assert _unnamed(r.text) == []


def test_disposition_form_macro_labels_every_control() -> None:
    src = (TEMPLATES / "_macros.html").read_text(encoding="utf-8")
    form = src[src.index("macro disposition_form") :]
    form = form[: form.index("endmacro")]
    # Macro ids use Jinja expressions; treat them as plain strings here.
    assert _unnamed(form) == []


def test_freeze_obligations_title_carries_product_name(client) -> None:
    r = client.get("/freeze-obligations")
    assert re.search(r"<title>[^<]*groAML[^<]*</title>", r.text)


def test_alerts_tabs_and_actions_are_separate_rows() -> None:
    src = (TEMPLATES / "alerts.html").read_text(encoding="utf-8")
    assert "tab-filter__tabs" in src and "tab-filter__actions" in src


def test_admin_and_freeze_pages_label_every_control(client) -> None:
    for path in ("/admin", "/freeze-obligations"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert _unnamed(r.text) == [], path


_BARE_SIBLING = re.compile(r"<label>[^<]*</label>\s*<(input|select|textarea)\b")


def test_labelled_templates_have_no_unassociated_sibling_labels() -> None:
    """customer/admin/dashboard/freeze templates: every <label> next to a control
    must carry `for` (a bare <label> beside an input labels nothing)."""
    for name in ("customer.html", "admin.html", "dashboard.html", "freeze_obligations.html"):
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        assert not _BARE_SIBLING.search(src), f"{name}: bare <label> beside a control"


def test_screen_page_lists_recent_checks_once_per_name(client) -> None:
    import re as _re
    tok = _re.search(r'name="csrf_token" value="([^"]+)"', client.get("/screen").text).group(1)
    for nm in ("Jane Roe", "jane roe", "John Doe"):
        r = client.post("/screen", data={"name": nm, "csrf_token": tok})
        assert r.status_code == 200
    page = client.get("/screen").text
    assert "Recent checks" in page
    assert page.count("/screen?name=") == 2      # Jane (once, newest spelling) and John
    assert "/screen?name=John%20Doe" in page


def test_screen_prefills_name_from_query_string(client) -> None:
    r = client.get("/screen?name=Jane%20Roe")
    assert 'value="Jane Roe"' in r.text


def test_recent_checks_never_cross_organisations(tmp_path, monkeypatch) -> None:
    """Recent checks are org-wide (every operator in a firm sees the firm's checks)
    but strictly per organisation: another firm never sees these names."""
    import re as _re
    from conftest import register_org
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    monkeypatch.setenv("AMLKIT_DB", str(tmp_path / "iso.db"))
    a, b = TestClient(app), TestClient(app)
    register_org(a, "Firm A", "Alice", "alice@firm-a.example")
    register_org(b, "Firm B", "Bob", "bob@firm-b.example")
    tok = _re.search(r'name="csrf_token" value="([^"]+)"', a.get("/screen").text).group(1)
    assert a.post("/screen", data={"name": "Secret Subject", "csrf_token": tok}).status_code == 200
    assert "Secret Subject" in a.get("/screen").text
    assert "Secret Subject" not in b.get("/screen").text
