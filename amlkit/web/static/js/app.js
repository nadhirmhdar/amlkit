/**
 * app.js - Core UI behaviors for amlkit
 * Extracted from base.html inline scripts for CSP compliance (Issue #82)
 */

// Form loading state - shows spinner on submit button
(function () {
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (form.classList.contains('no-loading')) return;
    var btn = form.querySelector('button[type="submit"]');
    if (!btn || form.classList.contains('is-submitting')) return;
    form.classList.add('is-submitting');
    var orig = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span>' + (btn.dataset.loading || 'Processing…');
    setTimeout(function () {
      form.classList.remove('is-submitting');
      btn.innerHTML = orig;
    }, 30000);
  });
}());

// User menu toggle (mobile header dropdown)
(function () {
  var wrap = document.getElementById('user-menu-wrap');
  function close() {
    if (!wrap) return;
    wrap.classList.remove('open');
    var btn = wrap.querySelector('.user-menu-btn');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }
  window.toggleUserMenu = function (e) {
    e.stopPropagation();
    if (!wrap) return;
    var opening = !wrap.classList.contains('open');
    wrap.classList.toggle('open');
    var btn = wrap.querySelector('.user-menu-btn');
    if (btn) btn.setAttribute('aria-expanded', String(opening));
  };
  document.addEventListener('click', function (e) {
    if (wrap && !wrap.contains(e.target)) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });
}());

// Desktop user menu toggle
(function () {
  var wrap = document.getElementById('desktop-user-menu-wrap');
  function close() {
    if (!wrap) return;
    wrap.classList.remove('open');
    var btn = wrap.querySelector('.user-menu-btn');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }
  window.toggleDesktopUserMenu = function (e) {
    e.stopPropagation();
    if (!wrap) return;
    var opening = !wrap.classList.contains('open');
    wrap.classList.toggle('open');
    var btn = wrap.querySelector('.user-menu-btn');
    if (btn) btn.setAttribute('aria-expanded', String(opening));
  };
  document.addEventListener('click', function (e) {
    if (wrap && !wrap.contains(e.target)) close();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') close();
  });
}());

// Feedback modal functions
function openFeedback() {
  document.getElementById('feedback-modal').style.display = 'block';
  document.getElementById('feedback-result').innerHTML = '';
  document.querySelector('#feedback-form textarea').focus();
}

function closeFeedback() {
  document.getElementById('feedback-modal').style.display = 'none';
  document.getElementById('feedback-form').reset();
  document.getElementById('feedback-result').innerHTML = '';
}

function submitFeedback(e) {
  e.preventDefault();
  var form = e.target;
  var formData = new FormData(form);
  var resultDiv = document.getElementById('feedback-result');
  resultDiv.innerHTML = '<span class="muted">Sending...</span>';
  fetch('/feedback', {
    method: 'POST',
    body: formData
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.success) {
      resultDiv.innerHTML = '<span style="color:#059669;">✓ ' + data.message + '</span>';
      form.reset();
      setTimeout(closeFeedback, 2000);
    } else {
      resultDiv.innerHTML = '<span style="color:#dc2626;">✗ ' + (data.error || 'Failed to send feedback.') + '</span>';
    }
  })
  .catch(function(err) {
    resultDiv.innerHTML = '<span style="color:#dc2626;">✗ Network error. Try again.</span>';
  });
}

// Close modal on click outside
window.addEventListener('click', function(e) {
  var modal = document.getElementById('feedback-modal');
  if (e.target === modal) closeFeedback();
});

// Generic confirm handler for buttons and forms with data-confirm attribute
function handleConfirm(e) {
  const message = e.currentTarget.getAttribute('data-confirm');
  if (message && !confirm(message)) {
    e.preventDefault();
    return false;
  }
  return true;
}

// Print button handler (evidence page)
function handlePrint() {
  window.print();
}

// Auto-submit form on select change (freeze_obligations page)
function handleAutoSubmit(e) {
  e.target.form.submit();
}

// Password strength indicator (register_organization page)
function checkStrength() {
  const pwd = document.getElementById('reg-password').value;
  const bar = document.getElementById('pwd-strength');
  let score = 0;
  if (pwd.length >= 10) score += 1;
  if (/[A-Z]/.test(pwd)) score += 1;
  if (/[0-9]/.test(pwd)) score += 1;

  if (score === 0) { bar.style.width = '0%'; }
  if (score === 1) { bar.style.width = '33%'; bar.style.background = 'var(--danger)'; }
  if (score === 2) { bar.style.width = '66%'; bar.style.background = 'var(--warn)'; }
  if (score === 3) { bar.style.width = '100%'; bar.style.background = 'var(--good)'; }
}

// Policy upload form toggle (policies page)
function toggleUploadForm() {
  const form = document.getElementById('upload-form');
  if (form.style.display === 'none') {
    form.style.display = 'block';
  } else {
    form.style.display = 'none';
  }
}

// Asset freeze execution: add asset row (freeze_execute_form page)
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

// Customer onboarding: toggle fields based on type (customer_new page)
function toggleCustomerFields() {
  const type = document.getElementById('customer_type').value;
  const isLegal = type === 'legal';

  // Toggle field visibility
  document.getElementById('field-gender').style.display = isLegal ? 'none' : '';
  document.getElementById('field-trade-licence').style.display = isLegal ? '' : 'none';

  // Update labels
  document.getElementById('label-nationality').textContent = isLegal ? 'Country of incorporation' : 'Nationality (ISO)';
  document.getElementById('label-birth-date').textContent = isLegal ? 'Date of incorporation' : 'Date of birth';

  // Toggle OCR section text
  const ocrTitle = document.querySelector('.ocr-upload-zone h3');
  const ocrDesc = document.querySelector('.ocr-upload-zone p');
  if (isLegal) {
    ocrTitle.textContent = 'Scan Trade Licence (OCR)';
    ocrDesc.textContent = 'Upload trade licence image to auto-fill company details.';
  } else {
    ocrTitle.textContent = 'Scan Passport (MRZ / OCR)';
    ocrDesc.textContent = 'Upload passport image to auto-fill name, DOB, nationality and gender.';
  }
}

async function performPassportOCR(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  const statusEl = document.getElementById('scan-status');
  statusEl.style.display = 'inline';
  statusEl.textContent = 'Scanning…';

  const formData = new FormData();
  formData.append('passport_file', file);
  formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

  try {
    const res = await fetch('/customers/scan-passport', {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error('Scan failed');
    const data = await res.json();

    // Auto-fill form fields
    if (data.full_name) {
      document.querySelector('input[name="full_name"]').value = data.full_name;
    }
    if (data.nationality) {
      // Find the hidden input that stores the country code (from country dropdown)
      var nationalityHidden = document.querySelector('input[name="nationality"][type="hidden"]');
      if (nationalityHidden) {
        nationalityHidden.value = data.nationality.substring(0, 2).toUpperCase();
        // Update display input too
        var nationalityDisplay = nationalityHidden.previousElementSibling;
        if (nationalityDisplay) {
          var code = data.nationality.substring(0, 2).toUpperCase();
          var country = window.COUNTRIES && window.COUNTRIES.find(function(c) { return c.code === code; });
          if (country) nationalityDisplay.value = country.name + ' (' + country.code + ')';
        }
      } else {
        // Fallback if country dropdown not initialized yet
        var nationalityInput = document.querySelector('input[name="nationality"]');
        if (nationalityInput) nationalityInput.value = data.nationality.substring(0, 2);
      }
    }
    if (data.birth_date) {
      document.querySelector('input[name="birth_date"]').value = data.birth_date;
    }
    if (data.gender) {
      document.querySelector('select[name="gender"]').value = data.gender;
    }

    const warnEl = document.getElementById('scan-authenticity');
    const flags = [
      ...((data.authenticity && data.authenticity.flags) || []),
      ...((data.expiry_check && data.expiry_check.flags) || []),
    ];
    if (flags.length > 0) {
      warnEl.textContent = 'Document check: ' + flags.join('; ') +
        '. Verify this document manually before relying on the extracted fields.';
      warnEl.style.display = 'block';
      statusEl.textContent = 'Scan complete — see warning below.';
    } else {
      warnEl.style.display = 'none';
      statusEl.textContent = data.authenticity
        ? 'Scan complete. MRZ checksums verified.'
        : 'Scan complete (MRZ not read — fields extracted via OCR fallback have no authenticity check).';
    }
  } catch (err) {
    statusEl.textContent = 'Scan failed. Please enter manually.';
  }
}

// Alerts drawer (p33)
function toggleAlertsDrawer() {
  var drawer = document.getElementById('alerts-drawer');
  if (!drawer) return;
  if (drawer.style.display === 'none') {
    drawer.style.display = 'block';
    loadAlertsDrawer();
  } else {
    drawer.style.display = 'none';
  }
}

function _el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

function _alertRow(href, tagClass, tagText, label) {
  var a = document.createElement('a');
  a.href = href;
  a.className = 'list-row';
  a.style.cssText = 'padding:6px 0;';
  var span = _el('span', 'tag ' + tagClass, tagText);
  span.style.cssText = 'width:90px;flex-shrink:0;font-size:11px;';
  a.appendChild(span);
  a.appendChild(_el('div', 'grow small', label));
  return a;
}

function loadAlertsDrawer() {
  var content = document.getElementById('alerts-drawer-content');
  if (!content) return;
  content.textContent = '';
  content.appendChild(_el('p', 'muted small', 'Loading...'));

  fetch('/api/alerts-summary')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      content.textContent = '';
      var badge = document.getElementById('alerts-badge');
      if (data.total > 0) {
        if (badge) { badge.textContent = data.total; badge.style.display = 'inline'; }

        if (data.screening_alerts && data.screening_alerts.length) {
          var h = _el('div', 'section-label', 'Screening alerts');
          h.style.marginBottom = '8px';
          content.appendChild(h);
          data.screening_alerts.forEach(function(a) {
            content.appendChild(_alertRow('/alerts', a.category, a.category, a.caption));
          });
        }
        if (data.transaction_alerts && data.transaction_alerts.length) {
          var h2 = _el('div', 'section-label', 'Transaction alerts');
          h2.style.cssText = 'margin:12px 0 8px;';
          content.appendChild(h2);
          data.transaction_alerts.forEach(function(a) {
            content.appendChild(_alertRow(
              '/customers/' + encodeURIComponent(a.customer_id),
              a.severity, a.rule_key.replace(/_/g, ' '), a.customer_name
            ));
          });
        }
        if (data.overdue_reviews && data.overdue_reviews.length) {
          var h3 = _el('div', 'section-label', 'Overdue reviews');
          h3.style.cssText = 'margin:12px 0 8px;';
          content.appendChild(h3);
          data.overdue_reviews.forEach(function(c) {
            var a = document.createElement('a');
            a.href = '/customers/' + encodeURIComponent(c.id);
            a.className = 'list-row';
            a.style.cssText = 'padding:6px 0;';
            a.appendChild(_el('div', 'grow small', c.full_name));
            a.appendChild(_el('div', 'side small muted', c.next_review));
            content.appendChild(a);
          });
        }
      } else {
        if (badge) badge.style.display = 'none';
        content.appendChild(_el('p', 'muted small', 'No open alerts.'));
      }
    })
    .catch(function() {
      content.textContent = '';
      var p = _el('p', 'muted small', 'Failed to load alerts.');
      p.style.color = 'var(--danger)';
      content.appendChild(p);
    });
}

// Customer search filter (customers page)
function filterCustomers(query) {
  const q = query.toLowerCase();
  const rows = document.querySelectorAll('.customer-row');
  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(q) ? '' : 'none';
  });
}

// Password toggle (login page)
function togglePassword() {
  const pwd = document.getElementById('password-input');
  const toggle = document.querySelector('[data-action="toggle-password"]');
  if (pwd && toggle) {
    const isPassword = pwd.type === 'password';
    pwd.type = isPassword ? 'text' : 'password';
    toggle.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
  }
}

// Wire up event handlers from data attributes
document.addEventListener('DOMContentLoaded', function() {
  // Password toggle button
  var passwordToggle = document.querySelector('[data-action="toggle-password"]');
  if (passwordToggle) {
    passwordToggle.addEventListener('click', togglePassword);
  }

  // Customer search input
  var customerSearch = document.querySelector('[data-action="filter-customers"]');
  if (customerSearch) {
    customerSearch.addEventListener('keyup', function(e) {
      filterCustomers(e.target.value);
    });
  }

  // Customer type toggle (customer_new page)
  var customerType = document.querySelector('[data-action="toggle-customer-fields"]');
  if (customerType) {
    customerType.addEventListener('change', toggleCustomerFields);
  }

  // Passport upload trigger button (customer_new page)
  var uploadBtn = document.querySelector('[data-action="trigger-passport-upload"]');
  if (uploadBtn) {
    uploadBtn.addEventListener('click', function() {
      var fileInput = document.getElementById('passport-upload');
      if (fileInput) fileInput.click();
    });
  }

  // Passport file input OCR (customer_new page)
  var passportInput = document.querySelector('[data-action="perform-ocr"]');
  if (passportInput) {
    passportInput.addEventListener('change', function(e) {
      performPassportOCR(e.target);
    });
  }

  // Add asset row button (freeze_execute_form page)
  var addAssetBtn = document.querySelector('[data-action="add-asset-row"]');
  if (addAssetBtn) {
    addAssetBtn.addEventListener('click', addAssetRow);
  }

  // Policy upload form toggle buttons (policies page)
  document.querySelectorAll('[data-action="toggle-upload-form"]').forEach(function(btn) {
    btn.addEventListener('click', toggleUploadForm);
  });

  // Password strength check (register_organization page)
  var regPassword = document.querySelector('[data-action="check-strength"]');
  if (regPassword) {
    regPassword.addEventListener('keyup', checkStrength);
  }

  // Print button handler
  document.querySelectorAll('[data-action="print"]').forEach(function(btn) {
    btn.addEventListener('click', handlePrint);
  });

  // Auto-submit select elements
  document.querySelectorAll('[data-action="auto-submit"]').forEach(function(select) {
    select.addEventListener('change', handleAutoSubmit);
  });

  // Confirm dialogs for buttons and forms
  document.querySelectorAll('[data-confirm]').forEach(function(el) {
    if (el.tagName === 'FORM') {
      el.addEventListener('submit', handleConfirm);
    } else {
      el.addEventListener('click', handleConfirm);
    }
  });

  // Feedback button
  var feedbackBtn = document.querySelector('[data-action="open-feedback"]');
  if (feedbackBtn) {
    feedbackBtn.addEventListener('click', openFeedback);
  }

  // Feedback close buttons
  document.querySelectorAll('[data-action="close-feedback"]').forEach(function(btn) {
    btn.addEventListener('click', closeFeedback);
  });

  // Feedback form submit
  var feedbackForm = document.getElementById('feedback-form');
  if (feedbackForm) {
    feedbackForm.addEventListener('submit', submitFeedback);
  }

  // User menu toggle (mobile)
  var userMenuBtn = document.querySelector('[data-action="toggle-user-menu"]');
  if (userMenuBtn) {
    userMenuBtn.addEventListener('click', window.toggleUserMenu);
  }

  // Desktop user menu toggle
  var desktopUserMenuBtn = document.querySelector('[data-action="toggle-desktop-user-menu"]');
  if (desktopUserMenuBtn) {
    desktopUserMenuBtn.addEventListener('click', window.toggleDesktopUserMenu);
  }

  // Alerts drawer buttons
  var alertsToggle = document.getElementById('alerts-drawer-toggle');
  if (alertsToggle) alertsToggle.addEventListener('click', toggleAlertsDrawer);
  var alertsClose = document.getElementById('alerts-drawer-close');
  if (alertsClose) alertsClose.addEventListener('click', toggleAlertsDrawer);
});
