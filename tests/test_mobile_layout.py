"""Phone-width layout regressions from the deployed-site UX review
(docs/reviews/2026-09-21-deployed-site-review/03-ux-design.md, items #9, #10).

These are server-side checks on the rendered markup and app.css -- the
browser measurements (no horizontal page scroll at 390px, operator name not
collapsed to 0px) depend on exactly these hooks being present:

* #9  /customers/{id}/evidence -- the screening-record and audit-trail tables
  carry the ``stack-table`` class, a marked header row and a ``data-label`` on
  every cell, so a phone shows each row as a label/value card. The stacking
  CSS is ``screen``-only so print and the WeasyPrint PDF keep the table.
* #10 /admin -- operator rows sit in a ``.grid-table`` (the stacked
  label/value pattern used elsewhere), with no fixed pixel widths as inline
  styles (which a phone stylesheet can't override), and the EU banner's
  ``<strong>`` sits inside one ``.banner__text`` span rather than being a
  bare flex child that renders as a side column.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest import register_org, seed_fresh_dataset  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
APP_CSS = ROOT / "amlkit" / "web" / "static" / "app.css"

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "source", "track", "wbr"}


class _Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children: list[_Node] = []
        self.text = ""

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def iter(self):
        yield self
        for c in self.children:
            yield from c.iter()

    def find_all(self, tag=None, cls=None):
        return [n for n in self.iter() if n is not self
                and (tag is None or n.tag == tag) and (cls is None or cls in n.classes)]

    def all_text(self) -> str:
        return self.text + "".join(c.all_text() for c in self.children)

    def ancestors(self):
        p = self.parent
        while p is not None:
            yield p
            p = p.parent


class _Tree(HTMLParser):
    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _Node("#root", {}, None)
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.text += data


def _parse(html: str) -> _Node:
    return _Tree(html).root


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Signed-in MLRO, two more operators, one screened customer."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("AMLKIT_DB", str(db_file))
    monkeypatch.delenv("AMLKIT_SINGLE_OPERATOR_MODE", raising=False)
    monkeypatch.delenv("AMLKIT_EU_FSF_TOKEN", raising=False)  # => EU banner shows
    from amlkit.db import connect
    conn = connect(str(db_file))
    seed_fresh_dataset(conn)
    conn.close()

    from fastapi.testclient import TestClient
    from amlkit.api.app import app
    c = TestClient(app)
    register_org(c, "Mobile Test Firm", "Reviewer MLRO", "reviewer.mlro@mobiletestfirm.ae")
    for name, email, role in [("Second Officer With Long Name", "second.officer@mobiletestfirm.ae", "officer"),
                              ("Third MLRO", "third@mobiletestfirm.ae", "mlro")]:
        c.post("/admin/operators", data={"name": name, "email": email, "password": "a-strong-password-2",
                                         "role": role, "csrf_token": c.cookies.get("amlkit_csrf")})
    return c


def _customer(client) -> int:
    r = client.post("/customers", data={
        "reference": "C-1", "full_name": "Ahmed Al Mansoori", "customer_type": "natural",
        "csrf_token": client.cookies.get("amlkit_csrf"),
    }, follow_redirects=True)
    assert r.status_code == 200
    return int(re.search(r"/customers/(\d+)", str(r.url)).group(1))


def _panel_table(doc: _Node, heading: str) -> _Node:
    for panel in doc.find_all("div", "panel"):
        h2 = panel.find_all("h2")
        if h2 and h2[0].all_text().strip() == heading:
            tables = panel.find_all("table")
            assert tables, f"no table under {heading!r}"
            return tables[0]
    raise AssertionError(f"panel {heading!r} not found")


# ---------------------------------------------------------------- UX #9

@pytest.mark.parametrize("heading", ["Screening record", "Audit trail"])
def test_evidence_tables_stack_on_phones(client, heading) -> None:
    cid = _customer(client)
    r = client.get(f"/customers/{cid}/evidence")
    assert r.status_code == 200
    table = _panel_table(_parse(r.text), heading)

    assert "stack-table" in table.classes
    assert any("table-responsive" in a.classes for a in table.ancestors()), \
        "keep the scroll wrapper as the fallback for wider-than-phone widths"
    rows = table.find_all("tr")
    head, body = rows[0], rows[1:]
    assert "stack-table__head" in head.classes
    labels = [th.all_text().strip() for th in head.find_all("th")]
    assert body, "fixture should have produced at least one row"
    for tr in body:
        cells = tr.find_all("td")
        assert [td.attrs.get("data-label") for td in cells] == labels


def test_evidence_stacking_css_is_screen_only() -> None:
    """Print/PDF keep the real table: stack-table rules live only under a
    ``screen`` phone media query."""
    css = APP_CSS.read_text(encoding="utf-8")
    blocks = re.findall(r"@media([^{]*)\{((?:[^{}]*\{[^{}]*\})*)[^{}]*\}", css)
    stacking = [q for q, body in blocks if ".stack-table" in body]
    assert stacking, "no media block styles .stack-table"
    for q in stacking:
        assert "screen" in q and "max-width" in q, q
    outside = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    assert ".stack-table" not in outside


# ---------------------------------------------------------------- UX #10

def _operator_rows(doc: _Node) -> list[_Node]:
    label = next(n for n in doc.find_all("div", "section-label") if n.all_text().strip() == "Operators")
    section = label.parent
    return [n for n in section.find_all("div", "list-row")]


def test_admin_operator_rows_use_stacked_grid_table(client) -> None:
    r = client.get("/admin")
    assert r.status_code == 200
    rows = _operator_rows(_parse(r.text))
    assert len(rows) == 3
    for row in rows:
        assert any("grid-table" in a.classes for a in row.ancestors()), \
            "operator rows must be inside .grid-table so phones stack them"
        cells = [c for c in row.children]
        assert "grow" in cells[0].classes and cells[0].all_text().strip()
        labelled = {c.attrs.get("data-label") for c in cells if c.attrs.get("data-label")}
        assert {"Email", "Role", "Status"} <= labelled
        # Fixed pixel widths as inline styles beat any phone stylesheet --
        # that is what squeezed the name column to 0px.
        for n in row.iter():
            assert "width" not in (n.attrs.get("style") or ""), (n.tag, n.attrs)


def test_admin_sanctions_rows_have_no_inline_widths(client) -> None:
    doc = _parse(client.get("/admin").text)
    label = next(n for n in doc.find_all("div", "section-label") if n.all_text().strip().startswith("Sanctions lists"))
    rows = label.parent.find_all("div", "list-row")
    assert rows
    for row in rows:
        for n in row.iter():
            assert "width" not in (n.attrs.get("style") or ""), (n.tag, n.attrs)


def test_admin_banner_text_flows_as_one_block(client) -> None:
    doc = _parse(client.get("/admin").text)
    banners = [b for b in doc.find_all("div", "banner") if "EU Sanctions Configuration" in b.all_text()]
    assert banners, "EU warning banner should render when AMLKIT_EU_FSF_TOKEN is unset"
    kids = banners[0].children
    assert len(kids) == 1 and "banner__text" in kids[0].classes
    assert kids[0].find_all("strong")


def test_admin_action_hints_drop_below_buttons_on_phones(client) -> None:
    html = client.get("/admin").text
    assert re.search(r'class="[^"]*\baction-hint\b[^"]*">Takes 30', html)
    css = APP_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.action-hint\s*\{[^}]*display:\s*block", css)
