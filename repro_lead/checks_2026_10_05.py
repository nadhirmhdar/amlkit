"""Lead repro, 2026-10-05: PEP alerts get the sanctions freeze note (mlro-user G1),
and the FATF resolver drops current grey-list names (compliance CS-6).

Read-only: no DB, no network. Exit 0 means both defects reproduce; 1 means at
least one is fixed.

    python repro_lead/checks_2026_10_05.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.WARNING)

from amlkit.ingest import fatf  # noqa: E402
from amlkit.queries import _category  # noqa: E402
from amlkit.screening.pf import classify_programs, obligation_note  # noqa: E402

# A PEP-list entity (e.g. CIA World Leaders) has a role.pep topic and no programs.
topics, programs = ["role.pep"], []
cat = _category(topics, programs)
note = obligation_note(classify_programs(programs))
print(f"PEP alert category={cat!r} obligation={note!r}")
g1 = cat == "pep" and "Freeze" in note

names = ["Kuwait", "Bolivia", "Nepal", "Papua New Guinea",
         "British Virgin Islands", "Virgin Islands (UK)", "Haiti", "Laos"]
dropped = [n for n in names if fatf._resolve_country(n) is None]
print(f"unmapped by fatf._resolve_country: {dropped}")
cs6 = bool(dropped)

print(f"G1 reproduces: {g1} | CS-6 reproduces: {cs6}")
sys.exit(0 if (g1 and cs6) else 1)
