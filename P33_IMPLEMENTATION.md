# P33 Implementation Guide: Alerts Drawer

## Status
- ✅ Tests written (test_p33_alerts_drawer.py)  
- ✅ Tests verified failing (RED step complete)
- ✅ Tests committed (commit cf89f02)
- ⏸️ Implementation (GREEN step) - documented below

## Tests Created
1. `test_base_template_has_alerts_drawer_toggle` - Verifies toggle button exists
2. `test_base_template_has_alerts_drawer_container` - Verifies drawer container exists
3. `test_alerts_drawer_defaults_to_hidden` - Verifies drawer hidden by default

All tests currently fail as expected.

## Implementation Steps (GREEN)

### 1. Add alerts drawer toggle button to base.html

In `amlkit/web/templates/base.html`, after the `.operator-box` (around line 50), add:

```html
    <button id="alerts-drawer-toggle" class="small" style="width:100%; margin-top:8px;" onclick="toggleAlertsDrawer()">
      Alerts <span id="alerts-count" class="badge" style="display:none;">0</span>
    </button>
  </aside>
```

### 2. Add alerts drawer container

After the closing `</aside>` tag (around line 51), add the drawer:

```html
  <div id="alerts-drawer" class="card" style="display:none; position:fixed; right:16px; top:16px; width:320px; max-height:80vh; overflow-y:auto; z-index:1000; box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);">
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
      <strong>Compliance Alerts</strong>
      <button class="small" onclick="toggleAlertsDrawer()" style="padding:4px 8px;">&times;</button>
    </div>
    
    <div id="alerts-content">
      <p class="muted small">No pending alerts.</p>
    </div>
  </div>
```

### 3. Add JavaScript toggle function

In the `<script>` section at the bottom of base.html (before `</body>`), add:

```javascript
function toggleAlertsDrawer() {
  var drawer = document.getElementById('alerts-drawer');
  if (drawer.style.display === 'none') {
    drawer.style.display = 'block';
    loadAlerts();
  } else {
    drawer.style.display = 'none';
  }
}

function loadAlerts() {
  // Placeholder for loading alerts via fetch
  // TODO: Implement backend endpoint /api/alerts
  var content = document.getElementById('alerts-content');
  content.innerHTML = '<p class="muted small">Loading alerts...</p>';
  
  // Mock data for now - replace with actual fetch
  setTimeout(function() {
    content.innerHTML = '<p class="muted small">No pending alerts.</p>';
  }, 500);
}
```

### 4. Verify tests pass

After making these changes:

```bash
cd C:/Users/nizam/amlkit && python -m pytest tests/test_p33_alerts_drawer.py -v
```

All 3 tests should pass.

### 5. Add backend route (optional for initial PR)

Create `/api/alerts` endpoint in `amlkit/api/app.py` to return JSON:

```python
@app.get("/api/alerts")
def get_alerts(session: Session = Depends(require_session)):
    conn = db()
    # Query pending compliance alerts, overdue deadlines, failed screenings
    alerts = []
    
    # Example: Get overdue customer reviews
    overdue = conn.execute("""
        SELECT id, full_name, next_review_date
        FROM customers
        WHERE org_id = ? AND next_review_date < date('now')
        LIMIT 5
    """, (session.org_id,)).fetchall()
    
    for row in overdue:
        alerts.append({
            "type": "deadline",
            "title": f"Review overdue: {row['full_name']}",
            "link": f"/customers/{row['id']}",
            "severity": "warning"
        })
    
    # Example: Get open high-severity alerts
    open_alerts = conn.execute("""
        SELECT id, caption, score
        FROM alerts
        WHERE org_id = ? AND status = 'open' AND score >= 0.9
        ORDER BY created_at DESC
        LIMIT 5
    """, (session.org_id,)).fetchall()
    
    for row in open_alerts:
        alerts.append({
            "type": "screening",
            "title": f"High match: {row['caption']}",
            "link": "/alerts",
            "severity": "danger"
        })
    
    conn.close()
    return {"alerts": alerts, "count": len(alerts)}
```

### 6. Update JavaScript to use backend

Replace the `loadAlerts()` placeholder with:

```javascript
function loadAlerts() {
  var content = document.getElementById('alerts-content');
  var badge = document.getElementById('alerts-count');
  content.innerHTML = '<p class="muted small">Loading...</p>';
  
  fetch('/api/alerts')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.count > 0) {
        badge.textContent = data.count;
        badge.style.display = 'inline';
        
        var html = '';
        data.alerts.forEach(function(alert) {
          var color = alert.severity === 'danger' ? '#dc2626' : '#f59e0b';
          html += '<a href="' + alert.link + '" class="list-row" style="border-left:3px solid ' + color + '; padding-left:8px;">';
          html += '<div class="grow small">' + alert.title + '</div>';
          html += '</a>';
        });
        content.innerHTML = html;
      } else {
        badge.style.display = 'none';
        content.innerHTML = '<p class="muted small">No pending alerts.</p>';
      }
    })
    .catch(function(err) {
      content.innerHTML = '<p class="muted small" style="color:#dc2626;">Failed to load alerts.</p>';
    });
}
```

### 7. Create draft PR

```bash
git add -A
git commit -m "feat: alerts drawer in sidebar (p33)

- Add alerts drawer toggle button in sidebar
- Drawer shows compliance alerts, deadlines, screening failures
- Uses existing CSS classes (.card, .badge, .list-row)
- JavaScript toggle with loadAlerts() placeholder
- Backend /api/alerts endpoint returns JSON

Tests: test_p33_alerts_drawer.py (all passing)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

git push -u origin feat/p33-alerts-drawer

gh pr create --draft --base master \
  --title "feat: alerts drawer for compliance notifications (p33)" \
  --body "## Summary
- Alerts drawer toggle button in sidebar
- Shows pending compliance alerts, overdue deadlines, failed screenings
- Uses existing CSS (.card, .badge, .list-row, .operator-box)
- JavaScript toggle with backend API integration
- Default hidden state

## Testing
- All tests passing: pytest tests/test_p33_alerts_drawer.py -v
- TDD approach: tests written first (RED), implementation follows (GREEN)

🤖 Coded via Bedrock (local CLI — no API key)

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

## Notes
- Implementation blocked by file edit persistence issue (same as p31/p32)
- Tests ready and committed
- Full implementation documented above for manual application
- Backend API endpoint optional for initial PR (can be placeholder)
