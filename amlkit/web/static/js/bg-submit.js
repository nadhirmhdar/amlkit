// Background submit with a loading glass, for forms marked data-bg-submit="screening|onboarding".
//
// The form posts with fetch, so the page does not reload while the check runs. A quick
// answer (under SHOW_AFTER) just swaps in; a slower one raises the glass, holds it at least
// MIN_HOLD so it never flickers, plays the server's verdict, and lowers it again.
//  - 200 HTML for the same page (screening): #main-content is swapped in place.
//  - {"location"} JSON (a redirect, see background_submit in app.py): the browser goes there
//    itself, so the flash message and that page's own scripts work as normal.
// The scene is 3D where WebGL works on a wide screen, 2D strands otherwise, and one still
// frame under reduced motion. Everything the glass says comes from the form or the server.
(function () {
  'use strict';
  if (window.__bgSubmit) return;
  window.__bgSubmit = true;

  var SHOW_AFTER = 400, MIN_HOLD = 1200, VERDICT_HOLD = 1500, EXIT = 600;
  // Read per check, so a preference changed mid-session is honoured. window.__bglMotion forces
  // the animated path for manual checks in a browser that reports reduced motion.
  var reduced = false;
  function readReduced() { reduced = !window.__bglMotion && !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches); }
  var CAPTIONS = ['Reading the name in every script', 'Matching spellings, aliases and transliterations',
    'Weighing date of birth and nationality', 'Separating near-misses from coincidences'];
  var STEPS = ['READING DOCUMENTS', 'MAPPING OWNERS', 'SCREENING EVERY PERSON', 'SCORING RISK'];

  var glOk = null;
  function webglAvailable() {
    if (glOk === null) {
      try { var c = document.createElement('canvas'); glOk = !!(c.getContext('webgl2') || c.getContext('webgl')); }
      catch (e) { glOk = false; }
    }
    return glOk;
  }
  // 3D only where it pays: WebGL present and a screen wide enough to show it (phones get the 2D strands).
  function wants3D() { return innerWidth >= 1000 && webglAvailable(); }
  var scenePromise = null;
  function loadScene() {
    if (!scenePromise) scenePromise = import('/static/js/loader-scene.js').catch(function () { return null; });
    return scenePromise;
  }
  document.addEventListener('focusin', function (e) {
    if (e.target.closest && e.target.closest('form[data-bg-submit]') && wants3D()) loadScene();
  });

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function scriptsOf(name) {
    var s = [];
    if (/[A-Za-z]/.test(name)) s.push('LATIN');
    if (/[؀-ۿ]/.test(name)) s.push('ARABIC');
    return s.length ? s : ['LATIN'];
  }

  // ------------------------------------------------------------------ the 2D fallback: strands into one line
  function strands2D(canvas, mode) {
    var ctx = canvas.getContext('2d'), raf = 0, t = 0, last = 0, verdict = null, vt = 0, dead = false;
    var seed = 7, rnd = function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    var n = mode === 'onboarding' ? 14 : 22, S = [];
    for (var i = 0; i < n; i++) S.push({ y: rnd(), a: .2 + rnd() * .6, f: 1 + rnd() * 2.5, p: rnd() * 6.3, s: .3 + rnd() * .5, risk: mode !== 'onboarding' && i % 7 === 3 });
    function size() { var r = Math.min(2, devicePixelRatio || 1); canvas.width = canvas.clientWidth * r; canvas.height = canvas.clientHeight * r; ctx.setTransform(r, 0, 0, r, 0, 0); }
    size(); addEventListener('resize', size);
    function draw() {
      var w = canvas.clientWidth, h = canvas.clientHeight, nx = w * .68, ny = h * .46;
      ctx.clearRect(0, 0, w, h); ctx.lineCap = 'round';
      var settle = verdict === 'clear' ? Math.min(1, vt) : 0;
      S.forEach(function (s) {
        var catchK = verdict === 'match' && s.risk ? Math.min(1, vt * 1.5) : 0;
        ctx.beginPath();
        for (var k = 0; k <= 60; k++) {
          var u = k / 60, x = u * nx, calm = Math.pow(1 - u, 1.5) * (1 - settle);
          var y = ny + (s.y - .5) * h * .8 * calm + Math.sin(u * s.f * 6.28 - t * s.s * 2 + s.p) * h * .07 * s.a * calm;
          if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        }
        ctx.strokeStyle = s.risk ? 'rgba(255,122,105,' + (.55 + catchK * .4) + ')' : 'rgba(78,204,211,' + (.18 + s.a * .35) + ')';
        ctx.lineWidth = s.risk ? 1.6 + catchK : 1.1;
        ctx.stroke();
      });
      ctx.strokeStyle = verdict === 'match' ? 'rgba(255,122,105,.9)' : 'rgba(78,204,211,.95)'; ctx.lineWidth = 2.4;
      ctx.beginPath(); ctx.moveTo(nx, ny); ctx.lineTo(w, ny); ctx.stroke();
      ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.arc(nx, ny, 5 + 2 * Math.pow(.5 + .5 * Math.sin(t * 3.2), 6), 0, 6.283); ctx.fill();
    }
    function loop(now) { if (dead) return; var dt = last ? Math.min(.05, (now - last) / 1000) : 1 / 60; last = now; t += dt; if (verdict) vt += dt * .8; draw(); raf = requestAnimationFrame(loop); }
    if (reduced) { t = 3; draw(); } else raf = requestAnimationFrame(loop);
    return {
      resolve: function (v) { verdict = v === 'match' ? 'match' : 'clear'; if (reduced) { vt = 1; draw(); } },
      destroy: function () { dead = true; cancelAnimationFrame(raf); removeEventListener('resize', size); },
    };
  }

  // ------------------------------------------------------------------ the glass
  function Glass(mode, name) {
    readReduced();
    this.mode = mode; this.name = name; this.scene = null; this.timers = [];
    var root = this.root = el('div', 'bgl' + (reduced ? ' bgl-still' : ''));
    root.setAttribute('data-mode', mode);
    root.appendChild(el('div', 'bgl-glass'));
    var layers = el('div', 'bgl-scene'); layers.setAttribute('aria-hidden', 'true'); root.appendChild(layers);
    this.layers = layers;
    root.appendChild(el('div', 'bgl-grain'));
    var hud = this.hud = el('div', 'bgl-hud');
    var status = el('div', 'bgl-status'); status.setAttribute('role', 'status');
    status.appendChild(el('i'));
    status.appendChild(el('span', '', mode === 'onboarding' ? 'ONBOARDING' : 'SCREENING · ' + scriptsOf(name).join(' + ') + ' SCRIPT'));
    hud.appendChild(status);
    var subject = el('div', 'bgl-subject');
    subject.appendChild(el('div', 'bgl-k', mode === 'onboarding' ? 'NEW CUSTOMER' : 'SUBJECT'));
    subject.appendChild(el('div', 'bgl-who', name)).setAttribute('dir', 'auto');
    if (mode === 'onboarding') {
      var steps = this.steps = el('div', 'bgl-steps');
      STEPS.forEach(function (s) { steps.appendChild(el('span', '', s)); });
      subject.appendChild(steps);
    } else {
      this.cap = subject.appendChild(el('div', 'bgl-cap', CAPTIONS[0]));
    }
    hud.appendChild(subject);
    this.hero = el('div', 'bgl-hero'); this.hero.setAttribute('aria-live', 'polite');
    hud.appendChild(this.hero);
    root.appendChild(hud);
  }
  Glass.prototype.every = function (ms, fn) { var id = setInterval(fn, ms); this.timers.push(id); };
  Glass.prototype.show = function () {
    var self = this;
    document.body.appendChild(this.root);
    document.documentElement.classList.add('bgl-open');
    // The hold counts from when the glass is actually on screen. Building the scene is heavy, so it
    // starts only after the glass has painted, rather than delaying it.
    this.shownAt = performance.now();
    this.visible = new Promise(function (done) {
      requestAnimationFrame(function () { requestAnimationFrame(function () {
        self.root.classList.add('live'); self.shownAt = performance.now(); done();
        setTimeout(function () { self.startScene(); }, 60);
      }); });
    });
    if (this.cap && !reduced) { var k = 1; this.every(2300, function () { self.cap.style.opacity = 0; setTimeout(function () { self.cap.textContent = CAPTIONS[k++ % CAPTIONS.length]; self.cap.style.opacity = 1; }, 250); }); }
    if (this.steps) {
      var spans = this.steps.children, i = 0;
      var tick = function () { for (var j = 0; j < spans.length; j++) spans[j].className = j < i ? 'done' : j === i ? 'now' : ''; i = Math.min(i + 1, spans.length - 1); };
      tick(); if (reduced) { tick(); } else this.every(1700, tick);
    }
  };
  Glass.prototype.startScene = function () {
    var self = this;
    function flat() {
      if (self.closed) return;
      var c = el('canvas', 'bgl-layer bgl-flat'); self.layers.appendChild(c);
      self.scene = strands2D(c, self.mode);
      if (self.pendingVerdict) self.scene.resolve(self.pendingVerdict);
    }
    if (!wants3D()) return flat();
    loadScene().then(function (mod) {
      if (self.closed) return;
      if (!mod) return flat();
      var gl = el('canvas', 'bgl-layer'), a = el('canvas', 'bgl-layer bgl-glow'), b = el('canvas', 'bgl-layer bgl-glow2');
      self.layers.appendChild(gl); self.layers.appendChild(a); self.layers.appendChild(b);
      try { self.scene = mod.mount({ canvas: gl, glowA: a, glowB: b, mode: self.mode, still: reduced }); }
      catch (e) { self.layers.textContent = ''; return flat(); }   // a context that will not start: draw it flat
      if (self.pendingVerdict) self.scene.resolve(self.pendingVerdict);
    });
  };
  Glass.prototype.verdict = function (v, title, line) {
    this.timers.forEach(clearInterval); this.timers = [];
    this.pendingVerdict = v;
    if (this.scene) this.scene.resolve(v);
    this.root.classList.add('resolved');
    if (v === 'match') this.root.classList.add('match');
    this.hero.textContent = '';
    this.hero.appendChild(el('div', 'bgl-k', this.mode === 'onboarding' ? 'ONBOARDING' : 'RESULT'));
    this.hero.appendChild(el('h2', '', title));
    if (line) this.hero.appendChild(el('p', '', line)).setAttribute('dir', 'auto');
    var hero = this.hero;
    requestAnimationFrame(function () { requestAnimationFrame(function () { hero.classList.add('on'); }); });
  };
  Glass.prototype.close = function () {
    var self = this;
    this.closed = true;
    this.timers.forEach(clearInterval);
    this.root.classList.add('out');
    setTimeout(function () {
      if (self.scene) self.scene.destroy();
      self.root.remove();
      document.documentElement.classList.remove('bgl-open');
    }, reduced ? 0 : EXIT);
  };

  // ------------------------------------------------------------------ submit
  function wait(ms) { return new Promise(function (r) { setTimeout(r, Math.max(0, ms)); }); }

  function showError(form, msg) {
    var old = form.querySelector('.bgl-error'); if (old) old.remove();
    var b = el('div', 'banner err bgl-error', msg); b.setAttribute('role', 'alert');
    form.insertBefore(b, form.firstChild);
  }

  function swapIn(doc) {
    var fresh = doc.getElementById('main-content'), main = document.getElementById('main-content');
    if (!fresh || !main) return false;
    main.innerHTML = fresh.innerHTML;
    if (doc.title) document.title = doc.title;
    if (window.initCountryDropdown) main.querySelectorAll('[data-country-dropdown]').forEach(function (i) { window.initCountryDropdown(i); });
    var res = main.querySelector('.screen-result');
    if (res) { res.setAttribute('tabindex', '-1'); res.focus({ preventScroll: true }); res.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' }); }
    return true;
  }

  function verdictFor(mode, outcome, name) {
    if (mode === 'screening' && outcome.doc) {
      var r = outcome.doc.querySelector('.screen-result[data-verdict]');
      if (!r) return null;
      var hits = parseInt(r.getAttribute('data-hits'), 10) || 0;
      return r.getAttribute('data-verdict') === 'match'
        ? ['match', hits === 1 ? 'Potential match.' : hits + ' potential matches.', 'Review before you proceed.']
        : ['clear', 'No match.', name + ' · screened and recorded'];
    }
    if (mode === 'onboarding' && outcome.location && /^\/customers\/\d+/.test(outcome.location)) {
      return ['clear', 'Customer onboarded.', name + ' · opening the record'];
    }
    return null;
  }

  async function run(form) {
    var mode = form.getAttribute('data-bg-submit');
    var field = form.querySelector(mode === 'onboarding' ? '[name="full_name"]' : '[name="name"]');
    var name = (field && field.value.trim()) || '';
    var btn = form.querySelector('button[type="submit"]'), label = btn && btn.innerHTML;
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>' + (btn.dataset.loading || 'Working…'); }
    form.setAttribute('aria-busy', 'true');
    var old = form.querySelector('.bgl-error'); if (old) old.remove();
    function restore() { if (btn) { btn.disabled = false; btn.innerHTML = label; } form.removeAttribute('aria-busy'); }

    var glass = new Glass(mode, name), shown = false;
    var showTimer = setTimeout(function () { shown = true; glass.show(); }, SHOW_AFTER);

    var outcome = {};
    try {
      var res = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin',
        headers: { 'X-Background-Submit': '1' } });
      var type = res.headers.get('content-type') || '';
      if (res.ok && type.indexOf('application/json') >= 0) outcome.location = (await res.json()).location;
      else if (res.ok && type.indexOf('text/html') >= 0 && new URL(res.url).pathname === location.pathname) outcome.doc = new DOMParser().parseFromString(await res.text(), 'text/html');
      else if (res.ok) outcome.location = res.url;
      else outcome.error = res.status === 429 ? 'Too many checks in a minute. Wait a moment and try again.'
        : 'The check did not complete (error ' + res.status + '). Nothing was changed on this page; try again.';
    } catch (e) {
      outcome.error = 'Could not reach groAML. Check the connection and try again.';
    }
    clearTimeout(showTimer);

    var v = outcome.error ? null : verdictFor(mode, outcome, name);
    if (shown) {
      await glass.visible;
      await wait(glass.shownAt + MIN_HOLD - performance.now());
      if (v) { glass.verdict(v[0], v[1], v[2]); await wait(reduced ? 900 : VERDICT_HOLD); }
    }
    if (outcome.location) { location.assign(outcome.location); return; }   // the glass stays up until the next page paints
    if (outcome.doc && swapIn(outcome.doc)) { if (shown) glass.close(); return; }
    if (shown) glass.close();
    restore();
    showError(form, outcome.error || 'The check did not complete. Try again.');
  }

  // Bubble phase on window, so field validators (and anything else) can cancel first.
  window.addEventListener('submit', function (e) {
    var form = e.target;
    if (e.defaultPrevented || !form.matches || !form.matches('form[data-bg-submit]')) return;
    if (!window.fetch || !window.DOMParser) return;   // very old browsers post the form normally
    e.preventDefault();
    if (form.getAttribute('aria-busy') === 'true') return;
    run(form);
  });

  // For screenshots and manual checks: window.__bgl.show('screening', 'Test Name'), then .resolve('match').
  window.__bgl = {
    show: function (mode, name) { var g = new Glass(mode || 'screening', name || 'Test Subject'); g.show(); this.g = g; return g; },
    resolve: function (v) { var g = this.g; if (!g) return; g.verdict(v, v === 'match' ? 'Potential match.' : g.mode === 'onboarding' ? 'Customer onboarded.' : 'No match.', g.name); },
    hide: function () { if (this.g) this.g.close(); this.g = null; },
  };
}());
