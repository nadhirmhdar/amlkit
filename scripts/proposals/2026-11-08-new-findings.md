# HELD proposal 2026-11-08 (SS1b, SS3b, SS4) -- not applied, no application code edited
Applies only when STRIPE_SECRET_KEY is set (open self-serve sign-up).
## SS1b timing oracle on /register-organization (amlkit/cases/operators.py register_organization -> _notify_existing_account)
An existing address returns in ~12 ms, a new one in ~76 ms (password hashing + inserts), although the page is identical. Do the same work on both paths: hash the submitted password (or a dummy of equal cost) before the existing-account branch, and send both mails from a background task so the request time does not depend on SMTP.
## SS3b notice and verification mail have no per-address cooldown
`send_existing_account_notice` and the verification mail go out on every submission (5/min/IP). Add one mail per address per hour (silent no-op after that, same page) so the form cannot be used to flood an inbox from many IPs.
## SS4 open sign-up now allows an organisation name identical to an existing firm (make_org_slug allow_duplicate_name)
Needed to keep the form from leaking which firms use the service, but it lets anyone create a workspace called "Dubai Gold Trading LLC". The name is only visible inside the new tenant; if names are ever shown to other parties (invites, exports, support views) show the slug or an "unverified name" marker.

## Addendum 2026-11-09 (SS3b confirmed, SS5)
SS5: the verification mail greets the address with the visitor-chosen display name verbatim ("Hi Mallory <b>bold</b> https://evil.test/pay,"). Anyone can therefore make groAML's sending domain deliver a message with their own text and URL to any address. Fix with SS3b: limit the greeting to a plain "Hi," (the name is not needed in a verification mail) or restrict the name to letters, spaces and common punctuation (no ``/``, ``:``, ``<``, ``>``, ``@``), and send at most one mail per address per hour.
