"""Issue #165 (as corrected by #313): customer page states the 10-year period.

Ten years is the firm's retention policy; Cabinet Resolution 134/2025
Art. 25(2) sets a five-year statutory minimum. See test_retention_policy.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_customer_detail_shows_ten_year_retention():
    """Issue #165: Customer page must show the 10-year retention policy."""
    template_path = Path(__file__).parent.parent / "amlkit" / "web" / "templates" / "customer.html"
    content = template_path.read_text().lower()

    assert "five years after" not in content, \
        "Template still states a five-year retention period"
    assert "10 years (firm policy" in content, \
        "Template should state the 10-year period as firm policy"
