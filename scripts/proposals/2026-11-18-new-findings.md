# HELD proposal 2026-11-18 (GV1) -- not applied, no application code edited
## GV1 no timeout on the Graphviz call (amlkit/cases/diagram.py: `dot.pipe()` at ~L110 and ~L156)
`graphviz.Digraph.pipe()` accepts a `quiet`/`encoding` argument but no timeout, so a hung `dot` process blocks the request thread for as long as it runs (30 s in my test with a stub that sleeps; the customer page then still returned 200). Missing or failing `dot` is handled (the helper returns None and the page renders without a diagram).
Fix: run `subprocess.run([...,"dot","-Tsvg"], input=src, timeout=10)` (or pass `dot.pipe(..., )` through a thread with a timeout) and treat `TimeoutExpired` like the existing fallback; log it. Low priority: layouts of at most 200 nodes finish in well under a second.
