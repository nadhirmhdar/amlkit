"""Small Latin/Cyrillic/Greek confusables map for identity comparison.

`fold_confusables(s)` maps lowercase Cyrillic and Greek letters that are
visually (near-)identical to a Latin letter onto that Latin letter, so that
"аlice" (Cyrillic а) and "alice" compare equal. It is for COMPARISON KEYS only
(duplicate / look-alike checks, reserved-name checks); never store its output
or show it to a user.

Contract: callers pass text that is already NFKC-normalised and casefolded
(see `auth.normalise_name_key`); only lowercase letters are mapped. Anything
not in the table passes through unchanged. Keep this file small and
self-contained: extend `_CONFUSABLES` below, one script per block, and add a
case to tests/test_operator_names.py for each new entry.
"""

from __future__ import annotations

_CONFUSABLES: dict[str, str] = {
    # Cyrillic -> Latin
    "а": "a", "в": "b", "с": "c", "ԁ": "d", "е": "e", "һ": "h", "н": "h",
    "і": "i", "ј": "j", "к": "k", "ӏ": "l", "м": "m", "о": "o", "р": "p",
    "ԛ": "q", "ѕ": "s", "т": "t", "ѵ": "v", "ԝ": "w", "х": "x", "у": "y",
    # Greek -> Latin
    "α": "a", "β": "b", "ε": "e", "η": "n", "ι": "i", "κ": "k", "μ": "u",
    "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "γ": "y",
    # Latin look-alikes that NFKC does not touch
    "ı": "i",  # dotless i
}

_TABLE = str.maketrans(_CONFUSABLES)


def fold_confusables(s: str) -> str:
    """Return `s` with Latin/Cyrillic/Greek look-alike letters folded to Latin."""
    return (s or "").translate(_TABLE)
