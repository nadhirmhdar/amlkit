"""Issue #165: Update retention copy from 5 to 10 years.

Cabinet Resolution No. 134 of 2025 extended UAE AML/CFT record retention
period from five to ten years. Customer detail page must reflect this.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_customer_detail_shows_ten_year_retention():
    """Issue #165: Customer page must show 10-year retention, not 5-year.
    
    Cabinet Resolution No. 134/2025 updated retention from 5 to 10 years.
    The customer detail template must reflect this update.
    """
    template_path = Path(__file__).parent.parent / "amlkit" / "web" / "templates" / "customer.html"
    content = template_path.read_text()
    
    # Must not mention "five year" or "5 year"
    assert "five year" not in content.lower(), \
        "Template still references 'five year' retention (should be 'ten year')"
    assert "5 year" not in content.lower(), \
        "Template still references '5 year' retention (should be '10 year')"
    
    # Must mention "ten year" or "10 year"  
    assert "ten year" in content.lower() or "10 year" in content.lower(), \
        "Template should reference 'ten year' or '10 year' retention per Cabinet Resolution No. 134/2025"
