# HELD: finding from the 2026-10-11 run (not applied; additive-only)
Evidence: reports/daily/2026-10-11/evidence/probe_auth_limits_on_0129848.txt (probe: repro_redteam/probe_auth_limits.py)

## A1 Unauthenticated account-lockout DoS against any known operator email (auth.py `login`, `MAX_FAILED_LOGINS = 8`, `LOCKOUT_MINUTES = 15`)
Eight wrong passwords lock the account for 15 minutes, and the limiter allows 3 attempts per minute per IP+email (`limits.py`), so an attacker with no credentials needs about 3 minutes to lock a known email, and can repeat every 15 minutes at 3 requests a minute. Probe: after 3 simulated minutes the MLRO's `failed_login_count` was 8 with `locked_until` set, and the correct password was then refused. An MLRO who cannot sign in cannot dispose a sanctions match or execute a freeze inside the 24-hour window.
Options (pick one or combine):
- Count failures per (account, source IP) for the lock decision, so a stranger's guesses cannot lock the account for the real user's IP; keep a smaller global per-account ceiling for distributed stuffing.
- Progressive delay instead of a hard 15-minute lock, and email the operator (and the org MLRO) on a lockout.
- Keep a documented break-glass route (UAE PASS SSO for MLRO, or `/system/create-operator` reset) for locked MLROs.

## INFO
- With `AMLKIT_BEHIND_PROXY=1`, `client_ip()` trusts the rightmost public hop. A request that reaches the container without a proxy-appended hop (a single spoofed `X-Forwarded-For` value) chooses its own rate-limit bucket (probe section 3: 14 of 14 login attempts accepted). Cloud Run's front end always appends the real client address, so this only matters if another ingress path to the container exists.
