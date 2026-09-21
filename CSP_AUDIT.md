# CSP Inline Script Audit - Issue #82

**Goal:** Remove `'unsafe-inline'` from `script-src` CSP header

**Current CSP:** `script-src 'self' 'unsafe-inline'`  
**Target CSP:** `script-src 'self'`

## Audit Results

### Templates with Inline Scripts (7)

1. **base.html** (~100 lines)
   - Form loading state handler (submit event listener)
   - User menu toggle logic
   - Theme toggle (dark/light mode)
   - Feedback modal open/close/submit
   - Disclaimer modal (first-login)

2. **customers.html**
   - Customer list filtering/search logic

3. **customer_new.html**  
   - Person type toggle (natural/legal)
   - Form validation/conditional fields

4. **freeze_execute_form.html**
   - Freeze obligation form handlers

5. **login.html**
   - Login form enhancements

6. **policies.html**
   - Policy document upload/management

7. **register_organization.html**
   - Registration form validation

### Inline Event Handlers (18 total)

**onclick handlers:**
- `base.html`: openFeedback(), closeFeedback(), toggleUserMenu()
- Multiple close buttons across modals

**onsubmit handlers:**
- `base.html`: submitFeedback(event)
- Form submission handlers in customer_new, freeze_execute_form

**Other:**
- Various form interaction handlers

## Migration Strategy

### Phase 1: Extract base.html scripts ✓ (audit complete)
Create `static/js/app.js` with:
- Form loading states (DOMContentLoaded → submit listener)
- User menu toggle
- Theme persistence
- Modal management

### Phase 2: Replace event handlers  
- Remove `onclick=` attributes
- Add `data-action` attributes or IDs
- Wire up via `addEventListener` in external JS

### Phase 3: Extract template-specific scripts
- customers.js, customer-form.js, policy-upload.js, etc.
- Load conditionally based on page

### Phase 4: Update CSP header
⚠️ Only after ALL inline scripts removed
- Change to `script-src 'self'`
- Verify no console errors

## Estimated Effort

- 7 templates × ~1 hour each = ~7 hours
- 18 event handlers × ~15 min each = ~4.5 hours
- Testing + CSP update = ~2 hours
- **Total: ~13-14 hours**

## Next Steps

1. Write failing test: template scanner that fails on inline scripts
2. Extract base.html scripts to static/js/app.js
3. Test theme toggle, modals, form loading states
4. Proceed template-by-template with tests after each
5. Update CSP header only when 100% clean
