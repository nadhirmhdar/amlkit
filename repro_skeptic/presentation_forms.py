"""Skeptic repro: Arabic presentation-form names canonicalise to '' (silent screening miss).
Exit 0 only if the defect reproduces."""
import sys, os, unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from amlkit.names.arabic import canonical_key, has_arabic_script
pf = "ﺏﻠﺎﻠ"          # presentation forms of Arabic letters (typical PDF copy-paste)
base = unicodedata.normalize("NFKC", pf)
print("has_arabic_script(pf):", has_arabic_script(pf), "| has_arabic_script(NFKC):", has_arabic_script(base))
print("canonical_key(pf)   =", repr(canonical_key(pf)))
print("canonical_key(NFKC) =", repr(canonical_key(base)))
sys.exit(0 if canonical_key(pf) == "" and canonical_key(base) != "" else 1)
