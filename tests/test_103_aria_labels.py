"""Test #103: Password toggle buttons have aria-label."""

from pathlib import Path


def test_login_password_toggle_has_aria_label():
    """Login page password toggle has aria-label."""
    template_path = Path(__file__).parent.parent / "amlkit" / "web" / "templates" / "login.html"
    content = template_path.read_text(encoding="utf-8")

    assert 'data-action="toggle-password"' in content, "Password toggle button should exist"
    assert 'aria-label="Toggle password visibility"' in content, "Password toggle must have aria-label"
