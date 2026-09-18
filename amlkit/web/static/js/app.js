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
