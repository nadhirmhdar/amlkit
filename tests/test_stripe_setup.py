"""scripts/stripe_setup.py and 'empty env = inert'. No network: Stripe's transport
is an httpx.MockTransport backed by a tiny in-memory Stripe."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amlkit.billing import service, stripe_client  # noqa: E402
from scripts import stripe_setup  # noqa: E402

URL = "https://groaml.grovisor.ae/billing/webhook"


class FakeStripe:
    def __init__(self):
        self.products, self.prices, self.hooks, self.calls = [], [], [], []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        form = {k: v[0] for k, v in parse_qs(request.content.decode(), keep_blank_values=True).items()}
        multi = parse_qs(request.content.decode())
        self.calls.append((method, path, form, request.headers.get("Authorization")))
        if method == "GET":
            coll = {"/v1/products": self.products, "/v1/prices": self.prices,
                    "/v1/webhook_endpoints": self.hooks}[path]
            q = dict(request.url.params)
            if "product" in q:
                coll = [p for p in coll if p["product"] == q["product"]]
            return httpx.Response(200, json={"data": coll, "has_more": False})
        if path == "/v1/products":
            obj = {"id": f"prod_{len(self.products)+1}", "name": form["name"],
                   "metadata": {"groaml_tier": form["metadata[groaml_tier]"]}}
            self.products.append(obj)
        elif path == "/v1/prices":
            obj = {"id": f"price_{len(self.prices)+1}", "product": form["product"],
                   "currency": form["currency"], "unit_amount": int(form["unit_amount"]),
                   "recurring": {"interval": form["recurring[interval]"],
                                 "interval_count": int(form["recurring[interval_count]"])}}
            self.prices.append(obj)
        elif path == "/v1/webhook_endpoints":
            obj = {"id": "we_1", "url": form["url"], "secret": "whsec_created_once",
                   "enabled_events": [v[0] for k, v in sorted(multi.items()) if k.startswith("enabled_events")]}
            self.hooks.append(obj)
        elif path.startswith("/v1/webhook_endpoints/"):
            obj = self.hooks[0]
            obj["enabled_events"] = [v[0] for k, v in sorted(multi.items()) if k.startswith("enabled_events")]
        else:
            return httpx.Response(404, json={"error": {"message": "nope"}})
        return httpx.Response(200, json=obj)

    def writes(self):
        return [c for c in self.calls if c[0] == "POST"]


@pytest.fixture()
def fake(monkeypatch):
    f = FakeStripe()
    monkeypatch.setattr(stripe_client, "_TRANSPORT", httpx.MockTransport(f))
    return f


CFG = stripe_client.StripeConfig(secret_key="sk_test_abc")


class TestSetupScript:
    def test_creates_yearly_aed_prices_and_webhook(self, fake):
        out = []
        values = stripe_setup.run(CFG, URL, dry_run=False, say=out.append)
        assert [p["name"] for p in fake.products] == ["groAML Starter", "groAML Professional"]
        got = {(p["unit_amount"], p["currency"], p["recurring"]["interval"]) for p in fake.prices}
        assert got == {(49900, "aed", "year"), (149900, "aed", "year")}
        assert values["STRIPE_PRICE_STARTER"] == "price_1"
        assert values["STRIPE_PRICE_PROFESSIONAL"] == "price_2"
        assert values["STRIPE_WEBHOOK_SECRET"] == "whsec_created_once"
        assert set(fake.hooks[0]["enabled_events"]) == set(service.HANDLED)
        assert all(c[3] == "Bearer sk_test_abc" for c in fake.calls)

    def test_second_run_creates_nothing(self, fake):
        stripe_setup.run(CFG, URL, dry_run=False, say=lambda _m: None)
        before = len(fake.writes())
        out = []
        values = stripe_setup.run(CFG, URL, dry_run=False, say=out.append)
        assert len(fake.writes()) == before
        assert values["STRIPE_PRICE_STARTER"] == "price_1"
        assert values["STRIPE_WEBHOOK_SECRET"] == ""
        assert any("WARNING" in m for m in out)

    def test_existing_webhook_with_wrong_events_is_corrected(self, fake):
        fake.hooks.append({"id": "we_1", "url": URL, "enabled_events": ["invoice.paid"]})
        stripe_setup.run(CFG, URL, dry_run=False, say=lambda _m: None)
        assert set(fake.hooks[0]["enabled_events"]) == set(service.HANDLED)

    def test_dry_run_writes_nothing(self, fake):
        out = []
        stripe_setup.run(CFG, URL, dry_run=True, say=out.append)
        assert fake.writes() == []
        assert sum("WOULD CREATE" in m for m in out) == 5

    def test_block_names_secrets_and_variables(self, fake):
        values = stripe_setup.run(CFG, URL, dry_run=False, say=lambda _m: None)
        block = stripe_setup.render_block(values, URL, dry_run=False)
        for name in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_STARTER",
                     "STRIPE_PRICE_PROFESSIONAL", "STRIPE_DISPLAY_PRICE_STARTER",
                     "STRIPE_DISPLAY_PRICE_PROFESSIONAL", "AMLKIT_BILLING_PUBLIC_URL"):
            assert name in block
        assert "AED 499 / year" in block and "AED 1,499 / year" in block
        assert "https://groaml.grovisor.ae" in block and "whsec_created_once" in block
        assert "ONCE" in block and "switch plans" in block
        assert "sk_test_abc" not in block

    def test_main_requires_key_and_valid_url(self, monkeypatch, capsys):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        assert stripe_setup.main(["--webhook-url", URL]) == 2
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        assert stripe_setup.main(["--webhook-url", "http://x.test/billing/webhook"]) == 2
        assert stripe_setup.main(["--webhook-url", "https://x.test/other"]) == 2

    def test_main_dry_run_end_to_end(self, fake, monkeypatch, capsys):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        assert stripe_setup.main(["--webhook-url", URL, "--dry-run"]) == 0
        assert "dry run" in capsys.readouterr().out and fake.writes() == []

    def test_stripe_error_exits_1(self, monkeypatch, capsys):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
        monkeypatch.setattr(stripe_client, "_TRANSPORT", httpx.MockTransport(
            lambda r: httpx.Response(401, json={"error": {"message": "Invalid API Key"}})))
        assert stripe_setup.main(["--webhook-url", URL]) == 1


class TestEmptyEnvIsInert:
    """The deploy passes every STRIPE_* name, empty when the repo secret/variable is unset."""

    ALL = ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_STARTER",
           "STRIPE_PRICE_PROFESSIONAL", "STRIPE_PRICE_CONSULTANT")

    def test_empty_and_whitespace_key_disables_billing(self, monkeypatch):
        for v in ("", "   "):
            for n in self.ALL:
                monkeypatch.setenv(n, v)
            assert stripe_client.load_config() is None
            from amlkit import billing
            assert billing.self_serve_enabled() is False

    def test_empty_price_ids_mean_tier_not_offered(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        for t in ("STARTER", "PROFESSIONAL", "CONSULTANT"):
            monkeypatch.setenv(f"STRIPE_PRICE_{t}", "")
        monkeypatch.setenv("STRIPE_PRICE_STARTER", "price_1")
        cfg = stripe_client.load_config()
        assert cfg.prices == {"starter": "price_1"}

    def test_empty_display_price_is_blank(self, monkeypatch):
        from amlkit.billing import plans
        monkeypatch.setenv("STRIPE_DISPLAY_PRICE_CONSULTANT", "")
        assert plans.display_price("consultant") == ""

    def test_workflow_passes_every_stripe_name_like_uaepass(self):
        wf = (ROOT / ".github/workflows/source-canary.yml").read_text()
        secrets = self.ALL
        variables = ("STRIPE_DISPLAY_PRICE_STARTER", "STRIPE_DISPLAY_PRICE_PROFESSIONAL",
                     "STRIPE_DISPLAY_PRICE_CONSULTANT", "AMLKIT_BILLING_PUBLIC_URL")
        for n in secrets:
            assert f"{n}: ${{{{ secrets.{n} }}}}" in wf
        for n in variables:
            assert f"{n}: ${{{{ vars.{n} }}}}" in wf
        for n in secrets + variables:
            assert f";;{n}=${{{n}}}" in wf
