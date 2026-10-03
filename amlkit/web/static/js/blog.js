// groAML blog behaviour. Progressive enhancement only: every page is fully
// readable with this script blocked. External file because CSP is
// script-src 'self' with no inline exceptions.
(function () {
  'use strict';

  // --- reading progress bar (article pages) ---------------------------
  var bar = document.querySelector('[data-bl-progress]');
  var article = document.querySelector('[data-bl-article]');
  var topLink = document.querySelector('[data-bl-top]');
  function onScroll() {
    if (bar && article) {
      var r = article.getBoundingClientRect();
      var total = article.offsetHeight - window.innerHeight;
      var done = Math.min(Math.max(-r.top / (total > 0 ? total : 1), 0), 1);
      bar.style.width = (done * 100).toFixed(1) + '%';
    }
    if (topLink) topLink.classList.toggle('is-on', window.scrollY > 900);
  }
  if (bar || topLink) {
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // --- table of contents scroll-spy ------------------------------------
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.bl-aside .bl-toc a'));
  if (tocLinks.length && 'IntersectionObserver' in window) {
    var byId = {};
    tocLinks.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var current = null;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          if (current) current.classList.remove('is-active');
          current = byId[e.target.id];
          if (current) current.classList.add('is-active');
        }
      });
    }, { rootMargin: '-90px 0px -70% 0px' });
    Object.keys(byId).forEach(function (id) {
      var h = document.getElementById(id);
      if (h) io.observe(h);
    });
  }

  // Close the mobile TOC after a jump so the reader lands on the section.
  document.querySelectorAll('.bl-toc-mobile a').forEach(function (a) {
    a.addEventListener('click', function () {
      var d = a.closest('details');
      if (d) d.open = false;
    });
  });

  // --- copy link / print -------------------------------------------------
  document.querySelectorAll('[data-bl-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.getAttribute('data-bl-copy') || window.location.href;
      var label = btn.querySelector('[data-label]');
      function done(text) {
        if (!label) return;
        var old = label.textContent;
        label.textContent = text;
        setTimeout(function () { label.textContent = old; }, 1800);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { done('Copied'); }, function () { done('Copy failed'); });
      } else {
        done('Copy failed');
      }
    });
  });
  document.querySelectorAll('[data-bl-print]').forEach(function (btn) {
    btn.addEventListener('click', function () { window.print(); });
  });
  // Printed copies should show every FAQ answer, not just the open ones.
  window.addEventListener('beforeprint', function () {
    document.querySelectorAll('.bl-faq details').forEach(function (d) {
      d.setAttribute('data-was-open', d.open ? '1' : '0');
      d.open = true;
    });
  });
  window.addEventListener('afterprint', function () {
    document.querySelectorAll('.bl-faq details[data-was-open]').forEach(function (d) {
      d.open = d.getAttribute('data-was-open') === '1';
      d.removeAttribute('data-was-open');
    });
  });

  // --- checklist: progress count, remembered on this device ------------
  document.querySelectorAll('[data-bl-checklist]').forEach(function (box) {
    var key = 'bl-check:' + box.getAttribute('data-bl-checklist');
    var inputs = Array.prototype.slice.call(box.querySelectorAll('input[type="checkbox"]'));
    var count = box.querySelector('[data-bl-check-count]');
    var saved = [];
    try { saved = JSON.parse(window.localStorage.getItem(key) || '[]'); } catch (e) { saved = []; }
    inputs.forEach(function (inp, i) { inp.checked = saved.indexOf(i) !== -1; });
    function update() {
      var on = [];
      inputs.forEach(function (inp, i) { if (inp.checked) on.push(i); });
      if (count) count.textContent = on.length + ' of ' + inputs.length + ' done';
      try { window.localStorage.setItem(key, JSON.stringify(on)); } catch (e) { /* storage blocked: fine */ }
    }
    inputs.forEach(function (inp) { inp.addEventListener('change', update); });
    update();
  });

  // --- blog index: instant search over the cards on the page -----------
  var search = document.querySelector('[data-bl-search]');
  if (search) {
    var cards = Array.prototype.slice.call(document.querySelectorAll('[data-bl-card]'));
    var empty = document.querySelector('[data-bl-noresults]');
    var feature = document.querySelector('[data-bl-feature-section]');
    search.addEventListener('input', function () {
      var q = search.value.trim().toLowerCase();
      var shown = 0;
      cards.forEach(function (c) {
        // The featured post also has a (normally hidden) grid card so that a
        // search, which hides the feature panel, can still find it.
        var dup = c.hasAttribute('data-bl-dup');
        var hit = q ? (c.getAttribute('data-bl-card') || '').indexOf(q) !== -1 : !dup;
        c.hidden = !hit;
        if (hit) shown++;
      });
      if (feature) feature.hidden = !!q;
      if (empty) empty.hidden = shown !== 0;
    });
  }
})();
