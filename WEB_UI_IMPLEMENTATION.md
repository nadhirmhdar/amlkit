# Phase 4 Item 6: Web UI Implementation Guide

This document specifies the Web UI routes and templates needed for TFS freeze obligation tracking. Implementation blocked by app.py import issues (slowapi module).

## Routes Required (amlkit/api/app.py)

### 1. List View: GET /freeze-obligations

```python
@app.get("/freeze-obligations")
def freeze_obligations_list(request: Request, db: Connection = Depends(get_db), session: dict = Depends(require_session)):
    """List all freeze obligations for current org.
    
    Filters:
    - status (query param): all | pending | executed | reported | resolved
    - Sort by: identified_at DESC (newest first)
    
    Template: freeze_obligations.html
    Context:
        - obligations: list of freeze obligation dicts
        - filter_status: current filter value
        - stats: {"pending": N, "executed": M, "reported": P, "resolved": Q}
    """
    org_id = session["org_id"]
    filter_status = request.query_params.get("status", "all")
    
    # Query freeze obligations
    query = """
        SELECT f.*, c.reference AS customer_reference, c.full_name,
               CAST((julianday('now') - julianday(f.identified_at)) * 24 AS INTEGER) AS hours_since_identified
        FROM freeze_obligations f
        JOIN customers c ON c.id = f.customer_id
        WHERE f.org_id = ?
    """
    params = [org_id]
    
    if filter_status != "all":
        query += " AND f.status = ?"
        params.append(filter_status)
    
    query += " ORDER BY f.identified_at DESC"
    
    obligations = [dict(row) for row in db.execute(query, params).fetchall()]
    
    # Get stats
    stats = dict(db.execute("""
        SELECT status, COUNT(*) as count
        FROM freeze_obligations
        WHERE org_id = ?
        GROUP BY status
    """, (org_id,)).fetchall())
    
    return templates.TemplateResponse("freeze_obligations.html", {
        "request": request,
        "obligations": obligations,
        "filter_status": filter_status,
        "stats": stats,
    })
```

### 2. Detail View: GET /freeze-obligations/{freeze_id}

```python
@app.get("/freeze-obligations/{freeze_id}")
def freeze_obligation_detail(
    freeze_id: int,
    request: Request,
    db: Connection = Depends(get_db),
    session: dict = Depends(require_session)
):
    """Show freeze obligation details with full lifecycle timeline.
    
    Template: freeze_obligation_detail.html
    Context:
        - obligation: freeze obligation dict
        - customer: customer dict
        - alert: source alert dict (if linked)
        - report: FFR report dict (if filed)
        - assets_frozen: parsed JSON list
        - can_execute: bool (status == 'pending_execution')
        - can_file_ffr: bool (status == 'executed_pending_report')
        - can_resolve: bool (status in ['executed_pending_report', 'reported'])
    """
    org_id = session["org_id"]
    
    # Fetch freeze obligation with joins
    row = db.execute("""
        SELECT f.*, c.reference AS customer_reference, c.full_name,
               a.id AS alert_id, a.matched_name,
               r.id AS report_id, r.reference AS report_reference
        FROM freeze_obligations f
        JOIN customers c ON c.id = f.customer_id
        LEFT JOIN alerts a ON a.id = f.alert_id
        LEFT JOIN reports r ON r.id = f.report_id
        WHERE f.id = ? AND f.org_id = ?
    """, (freeze_id, org_id)).fetchone()
    
    if not row:
        raise HTTPException(404, "Freeze obligation not found")
    
    obligation = dict(row)
    
    # Parse assets_frozen JSON
    import json
    obligation["assets_frozen_parsed"] = json.loads(obligation["assets_frozen"] or "[]")
    
    # Determine available actions
    can_execute = obligation["status"] == "pending_execution"
    can_file_ffr = obligation["status"] == "executed_pending_report"
    can_resolve = obligation["status"] in ["executed_pending_report", "reported"]
    
    return templates.TemplateResponse("freeze_obligation_detail.html", {
        "request": request,
        "obligation": obligation,
        "can_execute": can_execute,
        "can_file_ffr": can_file_ffr,
        "can_resolve": can_resolve,
    })
```

### 3. Execute Freeze: POST /freeze-obligations/{freeze_id}/execute

```python
@app.post("/freeze-obligations/{freeze_id}/execute")
def freeze_obligation_execute(
    freeze_id: int,
    request: Request,
    db: Connection = Depends(get_db),
    session: dict = Depends(require_session)
):
    """Execute freeze obligation - mark as executed with assets frozen.
    
    Form fields:
        - assets_frozen: JSON string or multiple fields:
          * asset_type_1, asset_identifier_1, asset_amount_1
          * asset_type_2, asset_identifier_2, asset_amount_2
          * ... (dynamic form rows)
        - notes: execution notes
    
    Requires: MLRO role
    Redirects to: /freeze-obligations/{freeze_id} with success message
    """
    if session["role"] != "mlro":
        raise HTTPException(403, "Execute freeze requires MLRO role")
    
    org_id = session["org_id"]
    operator = session["name"]
    
    # Parse form data
    form = await request.form()
    notes = form.get("notes", "")
    
    # Build assets_frozen list from form
    assets_frozen = []
    i = 1
    while f"asset_type_{i}" in form:
        asset_type = form[f"asset_type_{i}"]
        identifier = form[f"asset_identifier_{i}"]
        amount_str = form.get(f"asset_amount_{i}", "0")
        
        try:
            amount = float(amount_str) if amount_str else 0.0
        except ValueError:
            amount = 0.0
        
        if asset_type and identifier:
            assets_frozen.append({
                "type": asset_type,
                "identifier": identifier,
                "amount_aed": amount
            })
        i += 1
    
    # Call manager function
    from amlkit.cases import manager
    manager.execute_freeze(
        db,
        freeze_id,
        executed_by=operator,
        assets_frozen=assets_frozen,
        notes=notes
    )
    
    return RedirectResponse(
        f"/freeze-obligations/{freeze_id}?msg=freeze_executed",
        status_code=303
    )
```

### 4. File FFR: POST /freeze-obligations/{freeze_id}/file-ffr

```python
@app.post("/freeze-obligations/{freeze_id}/file-ffr")
def freeze_obligation_file_ffr(
    freeze_id: int,
    request: Request,
    db: Connection = Depends(get_db),
    session: dict = Depends(require_session)
):
    """Create FFR report from freeze obligation.
    
    Form fields:
        - reporter_name: MLRO full name
        - reporter_email: MLRO email
        - reporting_entity_name: optional
        - reporting_entity_branch: optional
    
    Creates:
        - New report row with report_type='FFR'
        - Links report to freeze obligation via report_id FK
        - Updates freeze obligation status='reported'
        - Generates goAML XML
    
    Requires: MLRO role
    Redirects to: /reports/{report_id}
    """
    if session["role"] != "mlro":
        raise HTTPException(403, "File FFR requires MLRO role")
    
    org_id = session["org_id"]
    operator = session["name"]
    
    # Fetch freeze obligation
    freeze = db.execute("""
        SELECT f.*, c.reference, c.full_name, c.customer_type,
               c.birth_date, c.gender, c.nationality, c.id_number, c.id_type
        FROM freeze_obligations f
        JOIN customers c ON c.id = f.customer_id
        WHERE f.id = ? AND f.org_id = ?
    """, (freeze_id, org_id)).fetchone()
    
    if not freeze or freeze["status"] != "executed_pending_report":
        raise HTTPException(400, "Freeze not ready for FFR filing")
    
    # Parse form
    form = await request.form()
    reporter_name = form.get("reporter_name") or operator
    reporter_email = form.get("reporter_email", "")
    
    # Build report payload
    import json
    report_payload = {
        "report_type": "FFR",
        "freeze_obligation_id": freeze_id,
        "customer_id": freeze["customer_id"],
        "obligation_type": freeze["obligation_type"],
        "identified_at": freeze["identified_at"],
        "executed_at": freeze["executed_at"],
        "assets_frozen": json.loads(freeze["assets_frozen"] or "[]"),
        "authority_ref": freeze["authority_ref"],
        "reporter_name": reporter_name,
        "reporter_email": reporter_email,
        "first_name": freeze["full_name"].split()[0],
        "last_name": " ".join(freeze["full_name"].split()[1:]),
        "customer_type": freeze["customer_type"],
        "reference": freeze["reference"],
        "birth_date": freeze["birth_date"],
        "gender": freeze["gender"],
        "nationality": freeze["nationality"],
        "id_number": freeze["id_number"],
        "id_type": freeze["id_type"],
    }
    
    # Generate goAML XML
    from amlkit.reporting import goaml
    xml_content = goaml.serialize_goaml_xml(report_payload)
    
    # Create report row
    from amlkit.db import utcnow
    now = utcnow()
    cursor = db.execute("""
        INSERT INTO reports
        (org_id, customer_id, report_type, status, payload, created_at)
        VALUES (?, ?, 'FFR', 'draft', ?, ?)
    """, (org_id, freeze["customer_id"], json.dumps(report_payload), now))
    report_id = cursor.lastrowid
    
    # Update freeze obligation
    db.execute("""
        UPDATE freeze_obligations
        SET report_id = ?, reported_at = ?, status = 'reported'
        WHERE id = ?
    """, (report_id, now, freeze_id))
    
    # Audit
    from amlkit.db import audit
    audit(db, operator, "freeze.reported", "freeze_obligation", str(freeze_id),
          {"report_id": report_id}, org_id=org_id)
    
    db.commit()
    
    return RedirectResponse(f"/reports/{report_id}", status_code=303)
```

### 5. Resolve: POST /freeze-obligations/{freeze_id}/resolve

```python
@app.post("/freeze-obligations/{freeze_id}/resolve")
def freeze_obligation_resolve(
    freeze_id: int,
    request: Request,
    db: Connection = Depends(get_db),
    session: dict = Depends(require_session)
):
    """Resolve (close) freeze obligation.
    
    Form fields:
        - resolution_reason: delisted | false_positive | authority_clearance
        - authority_ref: optional external reference
        - notes: resolution notes
    
    Requires: MLRO role
    Redirects to: /freeze-obligations/{freeze_id}
    """
    if session["role"] != "mlro":
        raise HTTPException(403, "Resolve freeze requires MLRO role")
    
    org_id = session["org_id"]
    operator = session["name"]
    
    form = await request.form()
    resolution_reason = form.get("resolution_reason")
    authority_ref = form.get("authority_ref", "")
    notes = form.get("notes", "")
    
    from amlkit.cases import manager
    manager.resolve_freeze_obligation(
        db,
        freeze_id,
        resolved_by=operator,
        resolution_reason=resolution_reason,
        authority_ref=authority_ref,
        notes=notes
    )
    
    return RedirectResponse(
        f"/freeze-obligations/{freeze_id}?msg=obligation_resolved",
        status_code=303
    )
```

## Templates Required (amlkit/web/templates/)

### 1. freeze_obligations.html

```html
{% extends "base.html" %}

{% block title %}Freeze Obligations{% endblock %}

{% block content %}
<div class="container">
  <h1>TFS Freeze Obligations</h1>
  
  <div class="alert alert-info">
    <strong>Cabinet Resolution 134/2025:</strong> Freeze obligations must be executed immediately.
    Personal liability applies to senior management for TFS compliance failures.
  </div>
  
  <!-- Stats Bar -->
  <div class="stats-bar">
    <span class="stat">Pending: {{ stats.get('pending_execution', 0) }}</span>
    <span class="stat">Executed: {{ stats.get('executed_pending_report', 0) }}</span>
    <span class="stat">Reported: {{ stats.get('reported', 0) }}</span>
    <span class="stat">Resolved: {{ stats.get('resolved', 0) }}</span>
  </div>
  
  <!-- Filter -->
  <form method="get" class="filter-form">
    <label>Status:</label>
    <select name="status" onchange="this.form.submit()">
      <option value="all" {% if filter_status == 'all' %}selected{% endif %}>All</option>
      <option value="pending_execution" {% if filter_status == 'pending_execution' %}selected{% endif %}>Pending Execution</option>
      <option value="executed_pending_report" {% if filter_status == 'executed_pending_report' %}selected{% endif %}>Executed (Pending Report)</option>
      <option value="reported" {% if filter_status == 'reported' %}selected{% endif %}>Reported</option>
      <option value="resolved" {% if filter_status == 'resolved' %}selected{% endif %}>Resolved</option>
    </select>
  </form>
  
  <!-- Table -->
  <table class="freeze-obligations-table">
    <thead>
      <tr>
        <th>Customer</th>
        <th>Type</th>
        <th>Risk</th>
        <th>Status</th>
        <th>Identified</th>
        <th>Executed</th>
        <th>Reported</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for ob in obligations %}
      <tr class="status-{{ ob.status }} {% if ob.status == 'pending_execution' and ob.hours_since_identified > 24 %}overdue{% endif %}">
        <td><a href="/customers/{{ ob.customer_id }}">{{ ob.customer_reference }}</a></td>
        <td>{{ ob.obligation_type }}</td>
        <td>
          {% if ob.risk_category == 'critical' %}
            <span class="badge badge-critical">🔴 CRITICAL</span>
          {% else %}
            <span class="badge badge-high">🟡 HIGH</span>
          {% endif %}
        </td>
        <td>
          {% if ob.status == 'pending_execution' and ob.hours_since_identified > 24 %}
            <strong class="overdue">OVERDUE ({{ ob.hours_since_identified }}h)</strong>
          {% else %}
            {{ ob.status | replace('_', ' ') | title }}
          {% endif %}
        </td>
        <td>{{ ob.identified_at[:10] }}</td>
        <td>{{ ob.executed_at[:10] if ob.executed_at else '—' }}</td>
        <td>{{ ob.reported_at[:10] if ob.reported_at else '—' }}</td>
        <td><a href="/freeze-obligations/{{ ob.id }}" class="btn btn-sm">View</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<style>
  .status-pending_execution { background-color: #fff3cd; }
  .status-pending_execution.overdue { background-color: #f8d7da; font-weight: bold; }
  .status-executed_pending_report { background-color: #d1ecf1; }
  .status-reported { background-color: #d4edda; }
  .status-resolved { background-color: #e2e3e5; }
  .overdue { color: #721c24; }
</style>
{% endblock %}
```

### 2. freeze_obligation_detail.html

```html
{% extends "base.html" %}

{% block title %}Freeze Obligation #{{ obligation.id }}{% endblock %}

{% block content %}
<div class="container">
  <h1>Freeze Obligation #{{ obligation.id }}</h1>
  
  <div class="obligation-header">
    <div class="field">
      <label>Customer:</label>
      <a href="/customers/{{ obligation.customer_id }}">{{ obligation.customer_reference }} - {{ obligation.full_name }}</a>
    </div>
    <div class="field">
      <label>Type:</label>
      {{ obligation.obligation_type | title }}
    </div>
    <div class="field">
      <label>Risk:</label>
      {% if obligation.risk_category == 'critical' %}
        <span class="badge badge-critical">🔴 CRITICAL</span>
      {% else %}
        <span class="badge badge-high">🟡 HIGH</span>
      {% endif %}
    </div>
    <div class="field">
      <label>Status:</label>
      <strong>{{ obligation.status | replace('_', ' ') | title }}</strong>
    </div>
  </div>
  
  <!-- Timeline -->
  <div class="timeline">
    <div class="timeline-item completed">
      <strong>✓ Identified</strong><br>
      {{ obligation.identified_at }}<br>
      by {{ obligation.identified_by }}
    </div>
    
    <div class="timeline-item {% if obligation.executed_at %}completed{% else %}pending{% endif %}">
      {% if obligation.executed_at %}
        <strong>✓ Executed</strong><br>
        {{ obligation.executed_at }}<br>
        by {{ obligation.executed_by }}
      {% else %}
        <strong>⏳ Pending Execution</strong><br>
        <em>Not yet executed</em>
      {% endif %}
    </div>
    
    <div class="timeline-item {% if obligation.reported_at %}completed{% else %}pending{% endif %}">
      {% if obligation.reported_at %}
        <strong>✓ Reported</strong><br>
        {{ obligation.reported_at }}<br>
        <a href="/reports/{{ obligation.report_id }}">Report #{{ obligation.report_id }}</a>
      {% else %}
        <strong>⏳ Pending Report</strong><br>
        <em>FFR not yet filed</em>
      {% endif %}
    </div>
    
    <div class="timeline-item {% if obligation.resolved_at %}completed{% else %}pending{% endif %}">
      {% if obligation.resolved_at %}
        <strong>✓ Resolved</strong><br>
        {{ obligation.resolved_at }}<br>
        by {{ obligation.resolved_by }}<br>
        Reason: {{ obligation.resolution_reason | replace('_', ' ') | title }}
      {% else %}
        <strong>⏳ Pending Resolution</strong>
      {% endif %}
    </div>
  </div>
  
  <!-- Assets Frozen (if executed) -->
  {% if obligation.assets_frozen_parsed %}
  <div class="section">
    <h2>Assets Frozen</h2>
    <table>
      <thead>
        <tr>
          <th>Type</th>
          <th>Identifier</th>
          <th>Amount (AED)</th>
        </tr>
      </thead>
      <tbody>
        {% for asset in obligation.assets_frozen_parsed %}
        <tr>
          <td>{{ asset.type | replace('_', ' ') | title }}</td>
          <td>{{ asset.identifier }}</td>
          <td>{{ "{:,.2f}".format(asset.amount_aed) }}</td>
        </tr>
        {% endfor %}
      </tbody>
      <tfoot>
        <tr>
          <th colspan="2">Total:</th>
          <th>{{ "{:,.2f}".format(obligation.assets_frozen_parsed | sum(attribute='amount_aed')) }}</th>
        </tr>
      </tfoot>
    </table>
  </div>
  {% endif %}
  
  <!-- Notes -->
  {% if obligation.notes %}
  <div class="section">
    <h2>Notes</h2>
    <p>{{ obligation.notes }}</p>
  </div>
  {% endif %}
  
  <!-- Action Buttons -->
  <div class="actions">
    {% if can_execute %}
      <a href="/freeze-obligations/{{ obligation.id }}/execute" class="btn btn-primary">Execute Freeze</a>
    {% endif %}
    
    {% if can_file_ffr %}
      <a href="/freeze-obligations/{{ obligation.id }}/file-ffr" class="btn btn-primary">File FFR Report</a>
    {% endif %}
    
    {% if can_resolve %}
      <a href="/freeze-obligations/{{ obligation.id }}/resolve" class="btn btn-secondary">Resolve Obligation</a>
    {% endif %}
    
    <a href="/freeze-obligations" class="btn">Back to List</a>
  </div>
</div>
{% endblock %}
```

### 3. freeze_execute_form.html (modal or separate page)

```html
<form method="post" action="/freeze-obligations/{{ freeze_id }}/execute">
  <h2>Execute Asset Freeze</h2>
  
  <div class="form-group">
    <label>Assets to Freeze:</label>
    <div id="assets-container">
      <div class="asset-row">
        <select name="asset_type_1">
          <option value="bank_account">Bank Account</option>
          <option value="investment_account">Investment Account</option>
          <option value="real_estate">Real Estate</option>
          <option value="cryptocurrency">Cryptocurrency</option>
          <option value="other">Other</option>
        </select>
        <input type="text" name="asset_identifier_1" placeholder="Account number / property address" required>
        <input type="number" name="asset_amount_1" placeholder="Amount (AED)" step="0.01">
      </div>
    </div>
    <button type="button" onclick="addAssetRow()">+ Add Asset</button>
  </div>
  
  <div class="form-group">
    <label>Execution Notes:</label>
    <textarea name="notes" rows="4" placeholder="Document freeze execution details..."></textarea>
  </div>
  
  <button type="submit" class="btn btn-primary">Execute Freeze</button>
  <a href="/freeze-obligations/{{ freeze_id }}" class="btn">Cancel</a>
</form>

<script>
let assetCount = 1;
function addAssetRow() {
  assetCount++;
  const container = document.getElementById('assets-container');
  const row = container.children[0].cloneNode(true);
  row.querySelectorAll('[name]').forEach(el => {
    el.name = el.name.replace(/_\d+$/, '_' + assetCount);
    if (el.tagName === 'INPUT') el.value = '';
  });
  container.appendChild(row);
}
</script>
```

## Navigation Integration (base.html)

Add to main navigation menu (MLRO-only):

```html
{% if session.role == 'mlro' %}
<li><a href="/freeze-obligations">Freeze Obligations</a></li>
{% endif %}
```

## Implementation Checklist

- [ ] Add routes to amlkit/api/app.py
- [ ] Create freeze_obligations.html template
- [ ] Create freeze_obligation_detail.html template
- [ ] Create freeze_execute_form.html (or modal)
- [ ] Create ffr_file_form.html (or modal)
- [ ] Create freeze_resolve_form.html (or modal)
- [ ] Add navigation link to base.html
- [ ] Add CSS styles for status colors
- [ ] Test all workflows:
  - [ ] List view with filters
  - [ ] Detail view shows timeline
  - [ ] Execute freeze with assets
  - [ ] File FFR creates report
  - [ ] Resolve closes obligation
- [ ] Add permission checks (MLRO-only)
- [ ] Add CSRF protection to all forms

## Notes

- All POST routes require MLRO role
- All routes enforce org_id isolation
- FFR filing creates report row and links to freeze obligation
- Status transitions are enforced by manager.py functions
- Overdue obligations (>24h) highlighted in red in list view
