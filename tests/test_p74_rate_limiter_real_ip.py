"""p74: Rate limiter uses real client IP, not reverse-proxy link-local address."""


def test_rate_limiter_uses_xforwardedfor_when_behind_proxy(monkeypatch):
    """rate_limit_key_func returns X-Forwarded-For IP when AMLKIT_BEHIND_PROXY=1."""
    monkeypatch.setenv("AMLKIT_BEHIND_PROXY", "1")

    import importlib, amlkit.api.app  # noqa: E401
    importlib.reload(amlkit.api.app)
    from amlkit.api.app import rate_limit_key_func

    class FakeRequest:
        headers = {"X-Forwarded-For": "203.0.113.42"}
        client = type("C", (), {"host": "169.254.1.1"})()

    assert rate_limit_key_func(FakeRequest()) == "203.0.113.42"


def test_rate_limiter_ignores_xforwardedfor_without_proxy_flag(monkeypatch):
    """Without AMLKIT_BEHIND_PROXY=1, X-Forwarded-For is ignored (anti-spoof)."""
    monkeypatch.delenv("AMLKIT_BEHIND_PROXY", raising=False)

    import importlib, amlkit.api.app  # noqa: E401
    importlib.reload(amlkit.api.app)
    from amlkit.api.app import rate_limit_key_func

    class FakeRequest:
        headers = {"X-Forwarded-For": "203.0.113.42"}
        client = type("C", (), {"host": "127.0.0.1"})()

    assert rate_limit_key_func(FakeRequest()) == "127.0.0.1"


def test_rate_limiter_takes_first_hop_from_chain(monkeypatch):
    """Multiple proxies: first IP in X-Forwarded-For is the real client."""
    monkeypatch.setenv("AMLKIT_BEHIND_PROXY", "1")

    import importlib, amlkit.api.app  # noqa: E401
    importlib.reload(amlkit.api.app)
    from amlkit.api.app import rate_limit_key_func

    class FakeRequest:
        headers = {"X-Forwarded-For": "203.0.113.42, 10.0.0.5, 10.0.0.6"}
        client = type("C", (), {"host": "169.254.1.1"})()

    assert rate_limit_key_func(FakeRequest()) == "203.0.113.42"


def test_login_rate_limit_key_uses_real_ip(monkeypatch):
    """login_rate_limit_key composes real IP + email, not proxy IP."""
    monkeypatch.setenv("AMLKIT_BEHIND_PROXY", "1")

    import importlib, amlkit.api.app  # noqa: E401
    importlib.reload(amlkit.api.app)
    from amlkit.api.app import login_rate_limit_key

    class FakeRequest:
        headers = {"X-Forwarded-For": "203.0.113.42"}
        client = type("C", (), {"host": "169.254.1.1"})()

        class state:
            login_email = "Test@Example.com"

    assert login_rate_limit_key(FakeRequest()) == "203.0.113.42:test@example.com"
