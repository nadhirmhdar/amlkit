"""Loading glass: screening and onboarding post in the background (bg-submit.js)."""
from __future__ import annotations

import re

from test_api import LISTED, _csrf, client  # noqa: F401  (client is the signed-in fixture)

BG = {"X-Background-Submit": "1"}


def test_screening_and_onboarding_forms_opt_in(client):
    screen = client.get("/screen").text
    assert re.search(r'<form[^>]*action="/screen"[^>]*data-bg-submit="screening"', screen)
    assert '<script src="/static/js/bg-submit.js"></script>' in screen
    new = client.get("/customers/new").text
    assert re.search(r'<form[^>]*action="/customers"[^>]*data-bg-submit="onboarding"', new)
    assert '<script src="/static/js/bg-submit.js"></script>' in new


def test_screening_result_carries_the_verdict_for_the_glass(client):
    hit = client.post("/screen", data={"name": LISTED, "csrf_token": _csrf(client)}, headers=BG).text
    assert re.search(r'class="screen-result" data-verdict="match" data-hits="[1-9]\d*"', hit)
    clear = client.post("/screen", data={"name": "Fictional Clearname Nobody", "csrf_token": _csrf(client)},
                        headers=BG).text
    assert 'class="screen-result" data-verdict="clear" data-hits="0"' in clear


def test_background_redirect_comes_back_as_json_with_its_flash_cookie(client):
    r = client.post("/customers", data={"reference": "BG-1", "full_name": "Fictional Test Trading LLC",
                                        "customer_type": "legal", "csrf_token": _csrf(client)},
                    headers=BG, follow_redirects=False)
    assert r.status_code == 200
    assert re.fullmatch(r"/customers/\d+", r.json()["location"])
    assert "set-cookie" in r.headers                     # the flash survives for the page the browser opens next
    assert r.headers["cache-control"] == "no-store"      # still wrapped by security_headers
    assert "content-security-policy" in r.headers
    page = client.get(r.json()["location"]).text
    assert "Onboarded" in page


def test_without_the_header_a_redirect_is_unchanged(client):
    r = client.post("/customers", data={"reference": "BG-2", "full_name": "Fictional Test Trading LLC",
                                        "customer_type": "legal", "csrf_token": _csrf(client)},
                    follow_redirects=False)
    assert r.status_code == 303 and re.fullmatch(r"/customers/\d+", r.headers["location"])


def test_expired_session_is_sent_to_sign_in_not_swapped_in(client):
    client.cookies.delete("amlkit_session")
    r = client.post("/screen", data={"name": LISTED, "csrf_token": _csrf(client)}, headers=BG,
                    follow_redirects=False)
    assert r.status_code == 200 and r.json() == {"location": "/login"}


def test_three_is_served_from_the_app_and_the_glass_names_no_lists(client):
    assert client.get("/static/vendor/three/three.module.js").status_code == 200
    scene = client.get("/static/js/loader-scene.js").text
    assert "from '../vendor/three/three.module.js'" in scene   # no CDN, no importmap (CSP is script-src 'self')
    js = client.get("/static/js/bg-submit.js").text + scene
    for name in ("OFAC", "FATF", "adverse media", "UN, ", "EOCN"):
        assert name not in js
    assert "https://" not in js
