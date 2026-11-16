"""Red-team 2026-11-16: Persian/Urdu/Pashto/Kurdish and Maghrebi letter variants of Arabic names vs the Latin listing. Each row replaces one letter (or adds a mark) in a baseline Arabic
spelling and checks the alert score against listed Latin names. LOCAL ONLY; pure functions."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from amlkit.match.scorer import name_score, DEFAULT_THRESHOLD
BASE = {"محمد عبد الله الكاظمي": ["Mohammed Abdullah Al Kadhimi", "Muhammad Abdallah al-Kazimi"], "يوسف كريم الحسيني": ["Yusuf Karim Al Husseini", "Youssef Kareem al-Hussaini"],
        "خالد بن هاشم القحطاني": ["Khalid bin Hashim Al Qahtani", "Khaled Hashem al-Qahtani"], "فاطمة الزهراء": ["Fatima Al Zahra", "Fatimah al-Zahraa"]}
SWAPS = [("ي", "ی", "Persian yeh"), ("ي", "ى", "alef maksura"), ("ك", "ک", "Persian kaf"), ("ك", "ڪ", "Sindhi kaf"), ("ه", "ہ", "Urdu heh"), ("ه", "ھ", "heh doachashmee"), ("ة", "ه", "teh marbuta->heh"),
         ("ة", "ت", "teh marbuta->teh"), ("ح", "ھ", "hah->heh doachashmee"), ("ا", "أ", "alef+hamza"), ("ا", "إ", "alef+hamza below"), ("ا", "آ", "alef madda"), ("ا", "ٱ", "alef wasla"), ("ق", "گ", "qaf->gaf"),
         ("ج", "چ", "jeem->cheh"), ("ب", "پ", "beh->peh"), ("ز", "ژ", "zain->zheh"), ("ف", "ڤ", "feh->veh"), ("ط", "ت", "tah->teh"), ("ض", "د", "dad->dal"), ("ظ", "ز", "zah->zain"), ("ث", "س", "theh->seen"),
         ("و", "ؤ", "waw+hamza"), ("ي", "ئ", "yeh+hamza"), ("ل", "ڵ", "Kurdish lam"), ("ر", "ڕ", "Kurdish reh"), ("ن", "ں", "noon ghunna"), ("ي", "ے", "yeh barree"), ("ذ", "ز", "thal->zain"), ("غ", "ع", "ghain->ain")]
EXTRA = [("tatweel inside", lambda s: s.replace("م", "مـ", 1)), ("shadda added", lambda s: s.replace("ل", "لّ", 1)), ("fatha on first letter", lambda s: s[0] + "َ" + s[1:]),
         ("Eastern-Arabic digit appended", lambda s: s + " ۱"), ("zero-width joiner in word", lambda s: s.replace("ع", "ع‍", 1)), ("NBSP separators", lambda s: s.replace(" ", " ")), ("two spaces", lambda s: s.replace(" ", "  "))]
miss, total = [], 0
for base, listed in BASE.items():
    ref = max(name_score(base, l)[0] for l in listed)
    print(f"baseline {base!r}: {ref:.2f}")
    variants = [(lab, base.replace(a, b, 1)) for a, b, lab in SWAPS if a in base] + [(lab, f(base)) for lab, f in EXTRA]
    for lab, v in variants:
        if v == base: continue
        total += 1; sc = max(name_score(v, l)[0] for l in listed)
        if sc < DEFAULT_THRESHOLD: miss.append((lab, base, round(sc, 2)))
print(f"\n{total} variants scored; below the {DEFAULT_THRESHOLD} alert threshold: {len(miss)}")
for lab, base, sc in miss: print(f"  MISS {sc:.2f}  {lab:28s} (from {base!r})")
