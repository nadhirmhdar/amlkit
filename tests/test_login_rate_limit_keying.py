"""Test that login rate limiting is keyed by IP + email, not just IP."""

from fastapi.testclient import TestClient
from amlkit.api.app import app


def test_different_emails_have_separate_rate_limits():
    """Multiple operators from the same IP should each get their own 3/minute budget."""
    client = TestClient(app)

    # Get CSRF token
    client.get("/login")
    csrf = client.cookies.get("amlkit_csrf")

    # Alice tries to login 3 times (exhaust her budget)
    for i in range(3):
        r = client.post("/login", data={
            "email": "alice@test.com",
            "password": "wrong",
            "csrf_token": csrf,
        })
        assert r.status_code in [200, 303], f"Alice attempt {i+1} should not be rate-limited"

    # Alice's 4th attempt should be blocked
    r = client.post("/login", data={
        "email": "alice@test.com",
        "password": "wrong",
        "csrf_token": csrf,
    })
    assert r.status_code == 429, "Alice's 4th attempt should be rate-limited"

    # Bob should still be able to login (different email = different rate limit bucket)
    r = client.post("/login", data={
        "email": "bob@test.com",
        "password": "wrong",
        "csrf_token": csrf,
    })
    assert r.status_code in [200, 303], "Bob's first attempt should not be rate-limited (different email)"


def test_same_email_shares_rate_limit_across_clients():
    """The same email from the same IP should share rate limit budget."""
    client1 = TestClient(app)
    client2 = TestClient(app)

    client1.get("/login")
    csrf1 = client1.cookies.get("amlkit_csrf")

    client2.get("/login")
    csrf2 = client2.cookies.get("amlkit_csrf")

    # Client1: 2 attempts for alice
    for i in range(2):
        r = client1.post("/login", data={
            "email": "alice2@test.com",
            "password": "wrong",
            "csrf_token": csrf1,
        })
        assert r.status_code in [200, 303]

    # Client2: 1 more attempt for alice (should work - 3rd attempt)
    r = client2.post("/login", data={
        "email": "alice2@test.com",
        "password": "wrong",
        "csrf_token": csrf2,
    })
    assert r.status_code in [200, 303], "Alice's 3rd attempt should work"

    # Client2: 4th attempt for alice (should be rate-limited)
    r = client2.post("/login", data={
        "email": "alice2@test.com",
        "password": "wrong",
        "csrf_token": csrf2,
    })
    assert r.status_code == 429, "Alice's 4th attempt should be rate-limited across both clients"
