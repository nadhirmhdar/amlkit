# HELD proposal 2026-10-16 (F6) -- not applied
## F6 POST /feedback has no length cap or rate limit (amlkit/api/app.py:2942)
Add `@limiter.limit("20/hour")` and cap `message` (e.g. 5,000 chars) and `page` (e.g. 200 chars) before insert; return 400 over the cap.
