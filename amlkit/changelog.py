"""/changelog support (p52): parse docs/CHANGELOG.md and track what an
operator has seen.

The file is a tiny Markdown subset -- '## heading' per release and '- ' bullets
-- so a minimal parser is used instead of a Markdown library. Every string is
escaped by Jinja when rendered, so the file cannot inject markup.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "docs" / "CHANGELOG.md"


def parse(text: str) -> list[dict]:
    """[{"title": str, "items": [str, ...]}, ...] in file order (newest first)."""
    entries: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            entries.append({"title": line[3:].strip(), "items": []})
        elif line.startswith(("- ", "* ")) and entries:
            entries[-1]["items"].append(line[2:].strip())
    return entries


@lru_cache(maxsize=1)
def _load() -> tuple[tuple[str, tuple[str, ...]], ...]:
    try:
        text = CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return ()
    return tuple((e["title"], tuple(e["items"])) for e in parse(text))


def entries() -> list[dict]:
    return [{"title": t, "items": list(i)} for t, i in _load()]


def latest() -> str | None:
    e = _load()
    return e[0][0] if e else None


def has_unseen(conn: sqlite3.Connection, operator_id: int) -> bool:
    cur = latest()
    if cur is None:
        return False
    row = conn.execute("SELECT changelog_seen FROM operators WHERE id=?",
                       (operator_id,)).fetchone()
    return row is not None and row["changelog_seen"] != cur


def mark_seen(conn: sqlite3.Connection, org_id: int, operator_id: int) -> None:
    cur = latest()
    if cur is None:
        return
    conn.execute("UPDATE operators SET changelog_seen=? WHERE id=? AND org_id=?",
                 (cur, operator_id, org_id))
    conn.commit()
