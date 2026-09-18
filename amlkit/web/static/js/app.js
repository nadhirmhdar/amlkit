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
      document.querySelector('input[name="nationality"]').value = data.nationality.substring(0, 2);
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
  if (pwd) {
    pwd.type = pwd.type === 'password' ? 'text' : 'password';
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

  // User menu toggle
  var userMenuBtn = document.querySelector('[data-action="toggle-user-menu"]');
  if (userMenuBtn) {
    userMenuBtn.addEventListener('click', window.toggleUserMenu);
  }
});
