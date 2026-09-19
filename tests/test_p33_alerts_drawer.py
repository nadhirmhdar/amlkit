"""Tests for p33: Alerts drawer in sidebar/header."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestAlertsDrawer:
    """Tests for alerts drawer showing compliance alerts, deadlines, screening failures."""

    def test_base_template_has_alerts_drawer_toggle(self) -> None:
        """Base template should have an alerts drawer toggle button."""
        base_path = Path(__file__).parent.parent / "amlkit" / "web" / "templates" / "base.html"
        content = base_path.read_text(encoding='utf-8')

        # Check for alerts drawer toggle button
        assert 'id="alerts-drawer-toggle"' in content or 'class="alerts-drawer-toggle"' in content, \
            "base.html missing alerts drawer toggle"

    def test_base_template_has_alerts_drawer_container(self) -> None:
        """Base template should have alerts drawer container."""
        base_path = Path(__file__).parent.parent / "amlkit" / "web" / "templates" / "base.html"
        content = base_path.read_text(encoding='utf-8')

        # Check for drawer container
        assert 'id="alerts-drawer"' in content or 'class="alerts-drawer"' in content, \
            "base.html missing alerts drawer container"

    def test_alerts_drawer_defaults_to_hidden(self) -> None:
        """Alerts drawer should default to hidden state."""
        base_path = Path(__file__).parent.parent / "amlkit" / "web" / "templates" / "base.html"
        content = base_path.read_text(encoding='utf-8')

        # Drawer should have hidden class or display:none style by default
        assert 'style="display:none"' in content or 'class="hidden"' in content, \
            "Alerts drawer should default to hidden"
