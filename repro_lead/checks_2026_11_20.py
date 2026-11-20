"""Lead checks 2026-11-20 (master bfb0253). Pure functions, no DB, no network.

DB1   exact name, same birth year, month typo -> silent (0.75) while a wrong year alerts (0.85)
CR49  UN adapter keeps only the first INDIVIDUAL_DATE_OF_BIRTH; a customer born on the
      listed *second* date (same year) takes the -0.25 penalty and is silent; an
      alternate in a different year scores 0.85 (alerts at zero margin)
PC1   two PEP-only hits with the same name tokens and no country on one side are folded
      into one (no identity signal: DOB is not compared)

Exit 0 while at least one item reproduces; exit 1 when all are fixed.
Run from the repo root: PYTHONPATH=. python repro_lead/checks_2026_11_20.py
"""
import sys

from amlkit.ingest.un import UNSanctionsAdapter
from amlkit.match.engine import Hit, collapse_pep_duplicates
from amlkit.match.scorer import DEFAULT_THRESHOLD, score_entity

NAME = "Ahmed Hassan Ali"
results = {}

# DB1
listed = "1975-03-04"
month_typo = score_entity(NAME, [NAME], query_birth_date="1975-08-04", cand_birth_date=listed)
wrong_year = score_entity(NAME, [NAME], query_birth_date="1995-03-04", cand_birth_date=listed)
print(f"DB1   month typo={month_typo.score:.2f}  wrong year={wrong_year.score:.2f}  threshold={DEFAULT_THRESHOLD}")
results["DB1"] = month_typo.score < DEFAULT_THRESHOLD <= wrong_year.score

# CR49
xml = b"""<CONSOLIDATED_LIST><INDIVIDUALS><INDIVIDUAL>
<DATAID>9001</DATAID><FIRST_NAME>AHMED</FIRST_NAME><SECOND_NAME>HASSAN</SECOND_NAME><THIRD_NAME>ALI</THIRD_NAME>
<INDIVIDUAL_DATE_OF_BIRTH><TYPE_OF_DATE>EXACT</TYPE_OF_DATE><DATE>1961-02-14</DATE></INDIVIDUAL_DATE_OF_BIRTH>
<INDIVIDUAL_DATE_OF_BIRTH><TYPE_OF_DATE>EXACT</TYPE_OF_DATE><DATE>1961-09-20</DATE></INDIVIDUAL_DATE_OF_BIRTH>
</INDIVIDUAL></INDIVIDUALS></CONSOLIDATED_LIST>"""
ent = next(iter(UNSanctionsAdapter().parse(xml)))
s = score_entity(NAME, [ent.caption], query_birth_date="1961-09-20", cand_birth_date=ent.birth_date)
print(f"CR49  UN entry with DOBs 1961-02-14 + 1961-09-20 stored birth_date={ent.birth_date!r};"
      f" customer born on the listed alternate 1961-09-20 scores {s.score:.2f}")
results["CR49"] = ent.birth_date == "1961-02-14" and s.score < DEFAULT_THRESHOLD

# PC1
a = Hit(entity_id=1, dataset="cia_leaders", caption="John Smith", schema_type="Person", score=1.0,
        matched_name="John Smith", topics=["role.pep"], detail={})
b = Hit(entity_id=2, dataset="wikidata_peps", caption="John Smith", schema_type="Person", score=1.0,
        matched_name="John Smith", topics=["role.pep"], detail={})
out = collapse_pep_duplicates([a, b], {1: ["GB"], 2: []})
print(f"PC1   two PEP hits 'John Smith' (GB vs no country) -> {len(out)} hit(s);"
      f" also_listed={[x.get('dataset') for x in out[0].detail.get('also_listed', [])]}")
results["PC1"] = len(out) == 1

for k, v in results.items():
    print(f"{k:5s} reproduces={v}")
n = sum(results.values())
print(f"{n}/{len(results)} reproduce")
sys.exit(0 if n else 1)
