# T-038: Fix issue #141 - Stop claiming STR/SAR was submitted to UAE FIU

HIGH priority compliance issue.

## Plan

1. **Check DB enum** - Verify if 'submitted' status is relied on in queries/templates
2. **Fix web flash message** - Change POST /reports/{id}/submit flash from "submitted to UAE FIU successfully" to state report is finalized and XML must be uploaded manually to FIU goAML portal
3. **Fix report_detail.html** - Update any matching wording about submission
4. **Fix mobile endpoint** - Change api/mobile.py response to include finalized:true, fiu_transmission:"manual", message field
5. **Add/update audit** - Use "report.finalized" audit action
6. **Write tests** - Assert neither web nor mobile responses contain "UAE FIU successfully" and both contain "goAML portal"
7. **Update existing tests** - Fix any tests expecting old wording
8. **Verify full suite** - pytest -x -q green
