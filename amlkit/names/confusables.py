"""Cyrillic / Greek -> Latin homoglyph folding for name screening and
operator-name comparison keys.

A name such as "BILAL ALI AL-ВAFI" (Cyrillic capital Ve in place of the
Latin B) is visually identical to the listed name but is a different string, so
it canonicalises to different tokens and silently misses the list. The table
below maps the Cyrillic and Greek letters that render (near-)identically to a
Latin letter onto that letter.

`fold_confusables` is the unconditional primitive (NFKC + map). Screening uses
`fold_mixed_script_tokens`, which only folds a token that is already Latin
(contains an ASCII letter) or that consists solely of mappable letters, so a
genuinely Cyrillic or Greek name is left alone and stays flagged as
unscreenable rather than being turned into Latin gibberish.
"""

from __future__ import annotations

import unicodedata

_CONFUSABLES: dict[str, str] = {
    # Cyrillic lower case
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w",
    "ѵ": "v", "ӏ": "l",
    # Cyrillic upper case
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y", "І": "I", "Ј": "J",
    "Ѕ": "S",
    # Greek upper case
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    # Greek lower case
    "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p",
    "τ": "t", "υ": "u", "χ": "x",
    # Lower-case look-alikes used by auth.operator_name_lookalike_key, which
    # casefolds before folding (operator duplicate / reserved-name checks).
    "в": "b", "н": "h", "к": "k", "м": "m", "т": "t",
    "β": "b", "η": "n", "μ": "u", "γ": "y",
    "ı": "i",  # dotless i: NFKC does not touch it
}


def fold_confusables(s: str) -> str:
    """NFKC-normalise, then map every Cyrillic/Greek homoglyph to its Latin twin."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    return "".join(_CONFUSABLES.get(ch, ch) for ch in s)


def _has_ascii_letter(tok: str) -> bool:
    return any(("a" <= ch <= "z") or ("A" <= ch <= "Z") for ch in tok)


def fold_mixed_script_tokens(s: str) -> str:
    """Fold homoglyphs only in tokens that are Latin-script in intent.

    A token is folded when it contains an ASCII letter (mixed-script spoof) or
    when every letter in it is a mappable homoglyph (an all-lookalike spoof).
    Tokens with any other Cyrillic/Greek letter are returned unchanged.
    """
    if not s or not any(ch in _CONFUSABLES for ch in s):
        return s
    out = []
    for part in s.split(" "):
        if any(ch in _CONFUSABLES for ch in part):
            letters = [ch for ch in part if ch.isalpha()]
            if _has_ascii_letter(part) or all(
                ch in _CONFUSABLES or ("a" <= ch <= "z") or ("A" <= ch <= "Z") for ch in letters
            ):
                part = "".join(_CONFUSABLES.get(ch, ch) for ch in part)
        out.append(part)
    return " ".join(out)
