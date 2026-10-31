"""Subscription tiers: who each is for and what it includes.

Limits are data on the Plan object. Prices are NOT here (or anywhere in the
code): the amount a customer pays lives in Stripe, referenced by the
STRIPE_PRICE_<TIER> price ID, and the human-readable price shown on /pricing
comes from the STRIPE_DISPLAY_PRICE_<TIER> env string. Changing a price is a
Stripe + config change, never a deploy of new code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

TRIAL_DAYS = 14
# After a failed payment or a cancellation the org keeps working for this long
# (writes included), then becomes read-only. Reads are never refused.
GRACE_DAYS = 7


@dataclass(frozen=True, slots=True)
class Plan:
    key: str
    name: str
    audience: str
    max_workspaces: int
    max_operators: int
    max_customers: int
    features: tuple[str, ...]

    def limit(self, resource: str) -> int:
        try:
            return {
                "workspaces": self.max_workspaces,
                "operators": self.max_operators,
                "customers": self.max_customers,
            }[resource]
        except KeyError:
            raise ValueError(f"unknown billable resource: {resource!r}") from None


_COMMON = (
    "Sanctions and PEP screening with Arabic-aware name matching",
    "Customer due diligence, risk assessment and audit trail",
    "goAML STR/SAR report export",
)

PLANS: dict[str, Plan] = {
    "starter": Plan(
        key="starter",
        name="Starter",
        audience="A single entity, natural person or independent professional.",
        max_workspaces=1, max_operators=3, max_customers=200,
        features=_COMMON,
    ),
    "professional": Plan(
        key="professional",
        name="Professional",
        audience="A single entity with a larger team and customer base.",
        max_workspaces=1, max_operators=10, max_customers=2000,
        features=_COMMON + ("Transaction monitoring and adverse media checks",),
    ),
    "consultant": Plan(
        key="consultant",
        name="Consultant",
        audience="A B2B consultant or outsourced MLRO running compliance for several client firms.",
        max_workspaces=20, max_operators=25, max_customers=10000,
        features=_COMMON + (
            "Up to 20 isolated client workspaces",
            "Transaction monitoring and adverse media checks",
        ),
    ),
}
TIERS: tuple[str, ...] = tuple(PLANS)


def get_plan(key: str | None) -> Plan | None:
    return PLANS.get(key or "")


def display_price(tier: str) -> str:
    """Price string shown on /pricing, e.g. "AED 499 / month". Empty when the
    deployer has not set STRIPE_DISPLAY_PRICE_<TIER> (the page then says
    "Contact us" rather than inventing a figure)."""
    return os.environ.get(f"STRIPE_DISPLAY_PRICE_{tier.upper()}", "").strip()
