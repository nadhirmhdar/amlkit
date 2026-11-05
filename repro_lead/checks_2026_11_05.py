"""Lead 2026-11-05: reproduce BD1 (mlro-user), CR-40/CI1 (code-reviewer, red-team) and
CS-5 (compliance) on current master. In-memory SQLite only; no network, no secrets.
Exit 0 when at least one reproduces (defect present), 1 when none do (all fixed)."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import logging; logging.disable(logging.CRITICAL)
from amlkit.db import connect, utcnow
from amlkit.cases.review import ReviewError, propose_disposition


def alert(conn, org_id, topic, n):
    now = utcnow()
    ds = conn.execute("INSERT INTO datasets (key, title, is_mandatory, last_refresh, entity_count)"
                      " VALUES (?,?,0,?,1) RETURNING id", (f"ds{n}", f"DS {n}", now)).fetchone()[0]
    eid = conn.execute("INSERT INTO entities (dataset_id, source_id, schema_type, caption, countries, topics,"
                       " programs, raw, first_seen, last_seen) VALUES (?,?,?,?,'[]',?,'[]','{}',?,?) RETURNING id",
                       (ds, f"E{n}", "Person", f"Subject {n}", f'["{topic}"]', now, now)).fetchone()[0]
    sid = conn.execute("INSERT INTO screenings (org_id, query_name, trigger, algorithm, threshold, run_at)"
                       " VALUES (?,?,'onboard','jaro_winkler',0.8,?) RETURNING id", (org_id, f"Subject {n}", now)).fetchone()[0]
    return conn.execute("INSERT INTO alerts (org_id, screening_id, entity_id, score, score_detail, matched_name,"
                        " status, created_at) VALUES (?,?,?,0.95,'{}',?,'open',?) RETURNING id",
                        (org_id, sid, eid, f"Subject {n}", now)).fetchone()[0]


hits = 0
conn = connect(":memory:")
org = conn.execute("INSERT INTO organizations (name, slug, status, created_at) VALUES ('F','f','active',?) RETURNING id",
                   (utcnow(),)).fetchone()[0]
cases = [("role.pep", "false_positive", "confirmed_match", ""),
         ("role.pep", "true_positive", "different_dob", "narrative given"),
         ("sanction", "false_positive", "confirmed_match", "")]
for i, (topic, status, code, narr) in enumerate(cases):
    a = alert(conn, org, topic, i)
    try:
        out = propose_disposition(conn, a, org_id=org, status=status, reason_code=code,
                                  operator="Op", operator_id=1, narrative=narr)
        row = conn.execute("SELECT status, disposition FROM alerts WHERE id=?", (a,)).fetchone()
        res = f"accepted -> alerts.status={row[0]!r} awaiting_second_review={out.awaiting_second_review}"
        hits += 1
    except ReviewError as e:
        res = f"refused ({str(e)[:60]})"
    print(f"BD1  {topic:9s} {status:15s} + {code:16s} narrative={bool(narr)!s:5s} -> {res}")
bd1 = hits > 0
print(f"BD1  reproduces={bd1} ({hits}/3 contradictory pairs accepted)")

wf = (ROOT / ".github/workflows/source-canary.yml").read_text()
on_pr = re.search(r"^  pull_request:", wf, re.M) is not None
jobs = {}
for m in re.finditer(r"^  ([a-z_-]+):\n((?:    .*\n|\s*\n)+)", wf, re.M):
    jobs[m.group(1)] = m.group(2)
leak = [j for j in ("sources", "heartbeat") if j in jobs
        and "secrets.EU_FSF_TOKEN" in jobs[j]
        and not re.search(r"^    if:.*", jobs[j], re.M)]
cr40 = on_pr and bool(leak)
print(f"CR40 workflow triggers on pull_request={on_pr}; jobs with EU_FSF_TOKEN and no job-level if: {leak}")
print(f"CR40 reproduces={cr40}")

sched = [x for t in re.findall(r'JOB_NAME="amlkit-sanctions-refresh"[\s\S]{0,2000}?--schedule "([^"]+)"[\s\S]{0,1200}?--schedule "([^"]+)"', wf) for x in t]
hours = []
for s in set(sched):
    h = s.split()[1]
    m = re.fullmatch(r"\*/(\d+)", h)
    hours = list(range(0, 24, int(m.group(1)))) if m else hours
gaps = [((hours[(i + 1) % len(hours)] - hours[i]) % 24) or 24 for i in range(len(hours))] if hours else []
cs5 = bool(gaps) and max(gaps) > 12
print(f"CS5  refresh schedule(s)={sorted(set(sched))}; fires at UTC hours {hours}; gaps(h)={gaps}")
print(f"CS5  reproduces={cs5}")

n = sum([bd1, cr40, cs5])
print(f"{n}/3 reproduce")
sys.exit(0 if n else 1)
