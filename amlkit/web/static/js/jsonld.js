// Injects schema.org JSON-LD at runtime so the page source itself carries no
// inline <script> block (CSP here is script-src 'self', no exceptions --
// see api/app.py). Data lives in a hidden [data-jsonld] element and is
// executed as soon as this external, 'self'-origin script runs.
document.querySelectorAll('[data-jsonld]').forEach(function (el) {
  var tag = document.createElement('script');
  tag.type = 'application/ld+json';
  tag.textContent = el.getAttribute('data-jsonld');
  document.head.appendChild(tag);
  el.remove();
});
