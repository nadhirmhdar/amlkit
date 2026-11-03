"""Self-serve subscription billing (Stripe). Optional and inert unless
STRIPE_SECRET_KEY is set -- see CLAUDE.md, "Billing (Stripe)"."""

from __future__ import annotations

# organizations.plan / plan_status of an org created through self-serve sign-up
# that has not added payment details yet (see billing.limits).
PENDING_PLAN = "none"
PENDING_STATUS = "pending_payment"


def self_serve_enabled() -> bool:
    """Single switch for the public sign-up mode.

    True  (Stripe configured): CTA "Start free trial" -> /register-organization,
          no invite code, new orgs start `pending_payment` until Checkout.
    False (no Stripe): CTA "Request access" -> /apply and the existing
          AMLKIT_REGISTRATION_INVITE_CODE gate on /register-organization.
    Read per call (env), like stripe_client.load_config().
    """
    from . import stripe_client
    return stripe_client.load_config() is not None
