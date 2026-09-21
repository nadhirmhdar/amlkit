"""Test for issue #143: rate limiter must skip private/link-local IPs in X-Forwarded-For.

On Cloud Run, X-Forwarded-For can start with a link-local (169.254.x.x) or
private (10.x.x.x, 172.16-31.x.x, 192.168.x.x) hop before the real client
IP. The rate limiter must use the first *public* IP so distinct tenants get
distinct rate-limit buckets.
"""

from __future__ import annotations


def _reload_and_get_client_ip(monkeypatch, behind_proxy: bool = True):
    if behind_proxy:
        monkeypatch.setenv("AMLKIT_BEHIND_PROXY", "1")
    else:
        monkeypatch.delenv("AMLKIT_BEHIND_PROXY", raising=False)

    from amlkit.api.deps import client_ip
    return client_ip


def _fake_request(xff: str, host: str = "169.254.1.1"):
    class FakeClient:
        pass
    c = FakeClient()
    c.host = host

    class FakeRequest:
        headers = {"X-Forwarded-For": xff}
        client = c

    return FakeRequest()


class TestRateLimiterSkipsPrivateIPs:
    def test_skips_link_local_first_hop(self, monkeypatch) -> None:
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req = _fake_request("169.254.8.129, 203.0.113.42")
        assert client_ip(req) == "203.0.113.42"

    def test_skips_rfc1918_10_prefix(self, monkeypatch) -> None:
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req = _fake_request("10.128.0.5, 198.51.100.7")
        assert client_ip(req) == "198.51.100.7"

    def test_skips_rfc1918_172_prefix(self, monkeypatch) -> None:
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req = _fake_request("172.16.0.1, 203.0.113.99")
        assert client_ip(req) == "203.0.113.99"

    def test_skips_rfc1918_192_168_prefix(self, monkeypatch) -> None:
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req = _fake_request("192.168.1.1, 203.0.113.50")
        assert client_ip(req) == "203.0.113.50"

    def test_skips_multiple_private_hops(self, monkeypatch) -> None:
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req = _fake_request("169.254.8.1, 10.0.0.5, 203.0.113.42")
        assert client_ip(req) == "203.0.113.42"

    def test_falls_back_to_last_ip_if_all_private(self, monkeypatch) -> None:
        """When all hops are private, return the rightmost (last) one."""
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req = _fake_request("10.0.0.1, 192.168.1.1")
        assert client_ip(req) == "192.168.1.1"

    def test_distinct_public_ips_get_distinct_buckets(self, monkeypatch) -> None:
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req_a = _fake_request("169.254.8.1, 203.0.113.10")
        req_b = _fake_request("169.254.8.1, 198.51.100.20")
        assert client_ip(req_a) != client_ip(req_b)

    def test_client_cannot_spoof_ip_by_prepending_fake_public_hop(self, monkeypatch) -> None:
        """Security: attacker prepends fake public IP to choose rate-limit bucket.

        XFF must be read RIGHT-TO-LEFT. If a client sends:
            X-Forwarded-For: 6.6.6.6, 203.0.113.42, 169.254.1.1

        The rightmost hop (169.254.1.1) is the one closest to our server (added by
        the reverse proxy). Moving left, 203.0.113.42 is the real client IP (public).
        The leftmost 6.6.6.6 was prepended by the client to fake their identity.

        Correct result: 203.0.113.42 (first public hop from the right)
        Vulnerable result: 6.6.6.6 (first public hop from the left - attacker wins)
        """
        client_ip = _reload_and_get_client_ip(monkeypatch)
        req = _fake_request("6.6.6.6, 203.0.113.42, 169.254.1.1")
        assert client_ip(req) == "203.0.113.42", \
            "Must return first public IP from RIGHT (203.0.113.42), not from LEFT (6.6.6.6)"

