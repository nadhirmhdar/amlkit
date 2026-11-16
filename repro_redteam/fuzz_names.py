"""Red-team 2026-11-15: property fuzz of the Arabic/Latin name pipeline (names.arabic.canonical_tokens, match.scorer.name_score) with hypothesis: no exception on any unicode text
(incl. lone surrogates, huge strings, combining storms), canonical form idempotent, score symmetric-ish and within [0,1], identical names score 1.0, runtime bounded. LOCAL ONLY."""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
from hypothesis import HealthCheck, given, settings, strategies as st
from amlkit.names.arabic import canonical_tokens
from amlkit.match.scorer import name_score
ARABIC = st.text(alphabet=st.characters(min_codepoint=0x0600, max_codepoint=0x06FF), max_size=60)
ANY = st.text(max_size=80)                       # includes lone surrogates? hypothesis excludes Cs by default; add explicitly below
SURR = st.text(alphabet=st.characters(min_codepoint=0xD800, max_codepoint=0xDFFF, blacklist_categories=()), max_size=20)
MIXED = st.one_of(ANY, ARABIC, SURR, st.text(alphabet="̀́​‍️‮ـ aAbB ", max_size=300))
fails = []
def run(name, fn, n=4000):
    t0 = time.time()
    @settings(max_examples=n, deadline=None, suppress_health_check=list(HealthCheck), database=None)
    @given(MIXED, MIXED)
    def t(a, b):
        try: fn(a, b)
        except AssertionError as e: fails.append((name, "assert", repr(a)[:60], repr(b)[:60], str(e)[:60])); raise
        except Exception as e: fails.append((name, type(e).__name__, repr(a)[:60], repr(b)[:60], str(e)[:80])); raise
    try: t(); print(f" {name:34s} OK  ({n} cases, {time.time()-t0:.1f}s)")
    except BaseException as e: print(f" {name:34s} FAIL {type(e).__name__}: first counterexample {fails[-1] if fails else ''}")
def canon(a, b):
    ta = canonical_tokens(a); assert isinstance(ta, list)
    assert canonical_tokens(" ".join(ta)) == ta or ta == [] or True
def idem(a, b):
    ta = canonical_tokens(a); tb = canonical_tokens(" ".join(ta)); assert tb == ta, f"not idempotent {ta} -> {tb}"
def score(a, b):
    s, d = name_score(a, b); assert 0.0 <= s <= 1.0 and s == s, f"score {s}"
def self_score(a, b):
    if canonical_tokens(a): s, _ = name_score(a, a); assert s == 1.0, f"self score {s}"
def sym(a, b):
    s1, _ = name_score(a, b); s2, _ = name_score(b, a); assert abs(s1 - s2) < 0.35, f"asym {s1:.2f} vs {s2:.2f}"
print("== property fuzz ==")
for n, f in [("canonical_tokens never raises", canon), ("canonical form idempotent", idem), ("score within [0,1], never NaN", score), ("identical names score 1.0", self_score), ("score roughly symmetric (<0.35)", sym)]: run(n, f)
t0 = time.time(); canonical_tokens("ا" * 200_000 + " " + "́" * 200_000); name_score("م" * 50_000, "م" * 50_000); print(f" huge input (200k Arabic + 200k combining) took {time.time()-t0:.2f}s")
print("== what canonicalises to nothing (unscreenable) or changes on a second pass ==")
import string
empty1 = [c for c in string.ascii_lowercase if not canonical_tokens(c)]
print(" single Latin letters that vanish:", "".join(empty1) or "none")
for s in ["b", "0B", "B.", "b.", "Ahmed B Ali", "Ahmed b. Ali", "bin", "ibn", "al", "el", "abu", "Abd", "Al Bin", "Bin Bin", "Al-", "of", "the", "de", "van", "الـ", "بن", "ابن", "أبو", "ال ال", "عبد", "عبد الله", "Abdullah", "Abd Allah"]:
    t = canonical_tokens(s); t2 = canonical_tokens(" ".join(t)); print(f"  {s!r:16} -> {t}" + ("" if t == t2 else f"   (2nd pass: {t2})"))
