"""Arabic name handling for sanctions screening.

This is the module the product's accuracy claim rests on. UAE screening is
dominated by Arabic-origin names arriving in three inconsistent forms:

  1. Arabic script, with or without diacritics    -> "محمد بن راشد"
  2. Latin transliteration, wildly variable       -> "Mohammed bin Rashid" / "Muhammad b. Rashed"
  3. Abbreviated Latin, common on UAE documents   -> "Mohd. B. Rashid"

Generic fuzzy matching handles none of these well. Levenshtein distance between
"Mohd" and "Muhammad" is 6 on an 8-character string -- no edit-distance
threshold can catch that without also matching half the database. The fix is
linguistic, not statistical: normalise to a form where the three variants above
collapse onto the same key, then let fuzzy matching work on what remains.

Design notes are inline where a rule is non-obvious, because every rule here is
a deliberate precision/recall trade-off that a reviewer may need to revisit.
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------
# Arabic script normalisation
# --------------------------------------------------------------------------

# Harakat (short-vowel diacritics), tatweel (kashida elongation), and the
# Quranic annotation range. All are decorative for matching purposes.
_ARABIC_DIACRITICS = re.compile(
    "["
    "ؐ-ؚ"  # Quranic annotations
    "ً-ٟ"  # harakat: fathatan..wavy hamza below
    "ٰ"         # superscript alef
    "ۖ-ۭ"  # more Quranic marks
    "]"
)
_TATWEEL = "ـ"

# Letter-form unification. Arabic writers vary hamza placement freely, and it
# is almost never a meaningful distinction between two people's names.
_ARABIC_LETTER_MAP = {
    "آ": "ا",  # alef madda      -> alef
    "أ": "ا",  # alef hamza above-> alef
    "إ": "ا",  # alef hamza below-> alef
    "ٱ": "ا",  # alef wasla      -> alef
    "ى": "ي",  # alef maksura    -> ya
    "ة": "ه",  # ta marbuta      -> ha
    "ؤ": "و",  # waw hamza       -> waw
    "ئ": "ي",  # ya hamza        -> ya
    "ء": "",        # standalone hamza-> drop
    # Persian/Urdu forms that appear in UAE data via expat populations
    "ک": "ك",  # keheh           -> kaf
    "ی": "ي",  # farsi ya        -> ya
    "ھ": "ه",  # heh doachashmee -> heh
}

_ARABIC_RANGE = re.compile(r"[؀-ۿݐ-ݿ]")

# Names that inherently start with "ال" or hamza-bearing variants as part of
# their root, not as a definite article prefix. Issue #139: these must be
# protected from article stripping.
_PROTECTED_AL_NAMES = frozenset({"الياس", "إلياس", "الهام", "إلهام", "الماس", "إلماس"})

# Arabic -> Latin transliteration.
#
# The goal is NOT scholarly romanisation; it is to land Arabic script in the
# same canonical space as the Latin transliterations that appear in sanctions
# lists, so a query in either script hits the same record. Values are therefore
# chosen to converge with common English spellings, not with ALA-LC.
_ARABIC_TRANSLIT = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j",
    "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r",
    "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "غ": "gh", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h",
    # Ain: dropping it entirely loses the leading vowel of names like
    # "Abdullah" and breaks the match. Mapping to "a" keeps them aligned.
    "ع": "a",
    "ﻻ": "la",
}

# Waw and ya are consonants word-initially ("Walid", "Yusuf") but long vowels
# elsewhere ("Maktoum", "Saeed"). Getting this wrong desynchronises the
# consonant skeleton, so they are resolved positionally.
_ARABIC_SEMIVOWELS = {"و": ("w", "u"), "ي": ("y", "i")}

# Direct Arabic-spelling lookup, consulted BEFORE transliteration.
#
# Reason: the consonant skeleton is lossy, and some distinct names collapse
# onto the same skeleton. "Hassan" (حسن) and "Hussein" (حسين) both reduce to
# h-s-n once short vowels are dropped, so a skeleton-only path silently
# resolves one into the other -- a wrong-person match, which in screening is a
# worse failure than no match at all.
#
# Arabic orthography keeps these names distinct, so where the query is already
# in Arabic there is no need to guess. Keys are post-`normalize_arabic` forms
# (diacritics stripped, alef/ya/ta-marbuta unified, leading "al-" removed).
ARABIC_FORMS: dict[str, str] = {
    "محمد": "mohammed",
    "احمد": "ahmed",
    "علي": "ali",
    "حسن": "hassan",
    "حسين": "hussein",
    "عبدالله": "abdullah",
    "عبدالرحمن": "abdulrahman",
    "عبدالعزيز": "abdulaziz",
    "ابراهيم": "ibrahim",
    "خالد": "khalid",
    "عمر": "omar",
    "سعيد": "saeed",
    "سالم": "salem",
    "راشد": "rashid",
    "سلطان": "sultan",
    "فاطمه": "fatima",
    "مريم": "mariam",
    "عايشه": "aisha",
    "يوسف": "youssef",
    "مصطفي": "mustafa",
    "ناصر": "nasser",
    "منصور": "mansour",
    "طارق": "tariq",
    "زايد": "zayed",
    "خليفه": "khalifa",
    "مكتوم": "maktoum",
    "نهيان": "nahyan",
    "حمدان": "hamdan",
    "صالح": "saleh",
    "داود": "dawood",
    "بلال": "bilal",
    "فواد": "fouad",
    "اسماعيل": "ismail",
    "نوره": "noura",
    "شيخه": "shaikha",
    "جاسم": "jassim",
    "سعد": "saad",
    "سلمان": "salman",
    "ماجد": "majid",
    "وليد": "walid",
    # Issue #139: Names that inherently start with alef-lam
    "الياس": "ilyas",
    "الهام": "ilham",
    "الماس": "almas",
}


def transliterate_arabic(token: str) -> str:
    """Romanise a single Arabic-script token into the Latin canonical space.

    Known Arabic spellings resolve directly to their canonical Latin name;
    only unknown tokens fall through to lossy consonant transliteration.
    """
    token = normalize_arabic(token)
    if token in ARABIC_FORMS:
        return ARABIC_FORMS[token]
    out: list[str] = []
    for i, ch in enumerate(token):
        if ch in _ARABIC_SEMIVOWELS:
            initial, medial = _ARABIC_SEMIVOWELS[ch]
            out.append(initial if i == 0 else medial)
        else:
            out.append(_ARABIC_TRANSLIT.get(ch, ""))
    return "".join(out)


def has_arabic_script(text: str) -> bool:
    """True if the string contains any Arabic-script character."""
    return bool(_ARABIC_RANGE.search(text or ""))


def normalize_arabic(text: str) -> str:
    """Collapse Arabic orthographic variation to a single canonical form.

    Removes diacritics and tatweel, unifies hamza-carrying letters, and strips
    the definite article "al-" when it is prefixed to a name token.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.replace(_TATWEEL, "")
    # Definite article stripping BEFORE hamza normalization. The article "ال"
    # always uses plain Alef (ا U+0627), never hamza forms (إ/أ/آ). Names like
    # "إلياس" (Ilyas) start with hamza-bearing Alef and are NOT articles.
    # Issue #139: stripping after hamza normalization corrupts these names.
    is_protected = any(text.startswith(name) for name in _PROTECTED_AL_NAMES)

    if not is_protected:
        text = re.sub(r"(?<![؀-ۿ])ال(?=[؀-ۿ]{3,})", "", text)
    text = "".join(_ARABIC_LETTER_MAP.get(ch, ch) for ch in text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# Latin transliteration handling
# --------------------------------------------------------------------------

# Name particles. These carry genealogical meaning ("son of", "daughter of")
# but are NOT distinguishing between individuals -- half of the UAE population
# has "bin" somewhere in their legal name. Treated as structure, not content.
PARTICLES = frozenset(
    {
        "bin", "ben", "ibn", "bn", "b",
        "bint", "binti", "binte", "bte",
        "al", "el", "ul", "ol", "as", "ash", "ad", "ar", "az", "an", "at",
        "abu", "abo", "aby", "abi", "umm", "um", "om",
        "van", "von", "de", "del", "della", "da", "di", "du", "la", "le",
    }
)

# "Servant of X" theophoric compounds. These fragment unpredictably across
# sources -- "Abdul Rahman", "Abdulrahman", "Abd al-Rahman", "AbdelRahman" are
# one name written four ways. Rejoining them before tokenisation prevents the
# fragments from being scored as separate name elements.
_ABD_FORMS = ("abdul", "abdel", "abdal", "abd", "abed", "abdu", "abdo")

# High-frequency UAE/GCC given names whose variants are too irregular for
# rule-based reduction. This table does the heavy lifting: these names cover a
# large share of real UAE screening traffic, so getting them exactly right
# matters more than elegance. Maps variant -> canonical key.
VARIANT_TABLE: dict[str, str] = {}


def _register(canonical: str, *variants: str) -> None:
    VARIANT_TABLE[canonical] = canonical
    for v in variants:
        VARIANT_TABLE[v] = canonical


# The single most important entry in this file: Mohammed is the most common
# given name on earth and the abbreviations ("mohd", "md") are unreachable by
# any edit-distance rule.
_register("mohammed", "mohamed", "muhammad", "mohammad", "muhammed", "mohamad",
          "muhamad", "muhamed", "mohammod", "mahammad", "mohd", "muhd", "mhd",
          "md", "mohmd", "moh'd", "mohammadi")
_register("ahmed", "ahmad", "ahmet", "ahamed", "ahammed", "achmad", "akhmad")
_register("ali", "aly", "aali", "ally")
_register("abdullah", "abdulla", "abdallah", "abdellah", "abdulah", "abdollah",
          "abdalla", "abdella", "abdulllah")
_register("abdulrahman", "abdurrahman", "abdelrahman", "abdalrahman",
          "abdurahman", "abdulrehman", "abdulrhman")
_register("abdulaziz", "abdelaziz", "abdulazeez", "abdalaziz")
_register("hassan", "hasan", "hassaan", "hasaan")
_register("hussein", "hussain", "husain", "husayn", "hosein", "hussien",
          "hussin", "hosain")
_register("ibrahim", "ebrahim", "ibraheem", "brahim", "ibrahem")
_register("khalid", "khaled", "kalid", "khaled", "chalid")
_register("omar", "umar", "omer", "oumar", "umer")
_register("saeed", "said", "sayed", "sayeed", "saed", "saied", "syed")
_register("salem", "salim", "saleem", "salm")
_register("sultan", "soltan", "sultaan")
_register("rashid", "rasheed", "rachid", "rashed", "rasheedh")
_register("hamdan", "hamdaan")
_register("maktoum", "maktum", "makhtoum")
_register("nahyan", "nahayan", "nehayan")
_register("zayed", "zaid", "zaied", "zayd")
_register("khalifa", "khalifah", "kalifa")
_register("mansour", "mansoor", "mansur")
_register("sheikh", "shaikh", "shaykh", "sheik")
_register("youssef", "yousef", "yusuf", "yousuf", "yusif", "joseph", "yousaf")
_register("ismail", "ismael", "esmail", "ismaeel")
_register("mustafa", "moustafa", "mostafa", "mustapha")
_register("jassim", "jasim", "qasim", "kassim", "qassim", "kasim")
_register("tariq", "tarek", "tarik", "tareq", "tariqu")
_register("nasser", "nasir", "naser", "nassir", "nassar")
_register("fatima", "fatimah", "fatma", "fathima", "fatema")
_register("aisha", "ayesha", "aishah", "aysha", "aicha")
_register("mariam", "maryam", "mariyam", "meriem", "maria")
_register("noura", "nora", "noor", "nur", "nour", "nourah")
_register("shaikha", "sheikha", "shaykha")
_register("latifa", "lateefa", "latifah")
_register("hind", "hend")
_register("sara", "sarah", "saara")
# Registered as canonicals in their own right. Without this they fall through
# to the consonant skeleton and get absorbed into a similar name -- "Saad"
# (سعد) was resolving to "Saeed" (سعيد), which is a different person.
_register("saad", "sad", "saade")
_register("saleh", "salih", "sale7")
_register("dawood", "daoud", "dawud", "daud", "davood")
_register("bilal", "belal", "bilaal")
_register("fouad", "foad", "fuad", "fouaad")
_register("salman", "selman", "salmaan")
_register("majid", "majed", "maged", "magid")
_register("walid", "waleed", "weleed")
# Issue #139: Names that start with alef-lam as part of their root
_register("ilyas", "elias", "ilias", "elyas")
_register("ilham", "elham")
_register("almas")


def canonical_token(token: str) -> str:
    """Map a single Latin name token to its canonical spelling.

    Resolution order:
      1. exact hit in the variant table  ("mohd"  -> "mohammed")
      2. skeleton hit against a known canonical name
         (transliterated Arabic "mhmd" -> skeleton "mhmd" -> "mohammed")
      3. bare consonant skeleton for everything else

    Step 2 is what makes cross-script matching work. Without it, Arabic script
    romanises to a vowel-free form that can never equal the vowel-rich Latin
    spellings held in the variant table.
    """
    t = token.lower().strip(".-'’")
    if not t:
        return ""
    if t in VARIANT_TABLE:
        return VARIANT_TABLE[t]
    skel = consonant_skeleton(t)
    return _SKELETON_INDEX.get(skel, skel)


# Digraphs must be reduced before vowel stripping, otherwise "kh" and "k"
# diverge and "Khalid"/"Kalid" stop matching.
_DIGRAPHS = (
    ("sch", "š"), ("sh", "š"), ("ch", "š"),
    ("kh", "ḫ"), ("gh", "ġ"), ("th", "θ"),
    ("dh", "ð"), ("ph", "f"), ("ck", "k"), ("qu", "k"),
    ("ee", "i"), ("oo", "u"), ("ou", "u"), ("aa", "a"), ("ei", "i"),
)

_VOWELS = set("aeiouy")


def consonant_skeleton(token: str) -> str:
    """Reduce a token to a vowel-light consonant skeleton.

    Arabic is a consonantal language; transliterated vowels are the least
    stable part of a romanised name and the most common source of spurious
    mismatches. Dropping them (except word-initially, which is perceptually
    salient) makes "Hussein"/"Hussain"/"Husayn" converge.
    """
    t = re.sub(r"[^a-z]", "", token.lower())
    if not t:
        return ""

    # Nisba (نسبة): a trailing -i/-y is a derivational suffix meaning "of/from",
    # and it is what turns a given name into a family name. "Mansour" (منصور)
    # and "Mansoori" (المنصوري) are different names, and Al Mansoori is one of
    # the most common Emirati surnames -- collapsing the two misfires across a
    # large share of the population. Stripping it as an ordinary final vowel
    # loses a genuine morpheme, so it is preserved as an explicit marker.
    nisba = len(t) > 3 and t.endswith(("i", "y"))

    for src, dst in _DIGRAPHS:
        t = t.replace(src, dst)
    head, tail = t[0], t[1:]

    # 'w' is dropped medially. Arabic waw is a consonant word-initially but a
    # long vowel elsewhere, and Latin transliterations render that same waw as
    # either "w" ("Hasnawi") or "ou/oo/u" ("Maktoum"). Dropping it medially on
    # both sides is what keeps the two scripts aligned.
    tail = "".join(ch for ch in tail if ch not in _VOWELS and ch != "w")

    out = head + tail
    # Collapse doubled consonants: "Abdullah" vs "Abdulah".
    out = re.sub(r"(.)\1+", r"\1", out)
    if nisba:
        out += "y"
    return out


# Reverse index from consonant skeleton back to canonical name, so
# transliterated Arabic can reach the same canonical forms as Latin.
#
# Ambiguous skeletons are deliberately EXCLUDED. "Hassan" and "Hussein" both
# reduce to h-s-n, as do "Saad" and "Saeed"; a first-registered-wins rule would
# silently resolve one into the other, which is a wrong-person match -- the
# worst failure available to a screening system, since it attaches a real
# person to someone else's designation.
#
# The cost is recall on unusual transliterations not present in the variant
# table: they keep their bare skeleton and will not reach the canonical form.
# That is the right side to err on, and the variant table covers the spellings
# that actually occur.
_AMBIGUOUS_SKELETONS: set[str] = set()
_SKELETON_INDEX: dict[str, str] = {}
for _canon in sorted(set(VARIANT_TABLE.values())):
    _skel = consonant_skeleton(_canon)
    if _skel in _SKELETON_INDEX and _SKELETON_INDEX[_skel] != _canon:
        _AMBIGUOUS_SKELETONS.add(_skel)
    else:
        _SKELETON_INDEX[_skel] = _canon
for _skel in _AMBIGUOUS_SKELETONS:
    _SKELETON_INDEX.pop(_skel, None)


# --------------------------------------------------------------------------
# Full-name processing
# --------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s؀-ۿ]", re.UNICODE)


def _rejoin_abd_compounds(tokens: list[str]) -> list[str]:
    """Merge "abdul" + "rahman" into a single token before canonicalisation."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in _ABD_FORMS and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            # Skip an intervening article: "abd al rahman".
            if nxt in ("al", "el", "ul") and i + 2 < len(tokens):
                out.append("abdul" + tokens[i + 2])
                i += 3
                continue
            out.append("abdul" + nxt)
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def tokenize(name: str) -> tuple[list[str], list[str]]:
    """Split a name into (content tokens, particle tokens).

    Particles are kept rather than discarded: they are weak evidence on their
    own but useful as a tie-breaker between two otherwise equal candidates.
    """
    if not name:
        return [], []
    if has_arabic_script(name):
        # Romanise per token before anything else, so particle detection,
        # theophoric rejoining and the variant table all operate in one script.
        name = normalize_arabic(name)
        name = " ".join(
            transliterate_arabic(tok) if has_arabic_script(tok) else tok
            for tok in name.split()
        )
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT.sub(" ", text).lower()
    raw = [t for t in text.split() if t]

    particles = [t for t in raw if t in PARTICLES]
    content = [t for t in raw if t not in PARTICLES]
    content = _rejoin_abd_compounds(content)
    return content, particles


def canonical_tokens(name: str) -> list[str]:
    """Canonical, order-independent token list for a full name."""
    content, _ = tokenize(name)
    return [c for c in (canonical_token(t) for t in content) if c]


def canonical_key(name: str) -> str:
    """Order-independent fingerprint of a name.

    Sorting the tokens is what makes "Rashid Mohammed" match "Mohammed Rashid".
    Arabic name chains routinely arrive in different orders across documents,
    so order must not be load-bearing.
    """
    return " ".join(sorted(canonical_tokens(name)))


def blocking_keys(name: str) -> set[str]:
    """Cheap keys for candidate generation.

    Screening cannot afford to score a query against every record, so we first
    retrieve anything sharing a canonical token. Recall here bounds the recall
    of the whole system -- it is deliberately generous.
    """
    toks = canonical_tokens(name)
    keys = set(toks)
    for t in toks:
        if len(t) >= 4:
            keys.add(t[:4])
    return {k for k in keys if k}
