// Sign-in decoration: noisy strands drift in from the left, calm down and
// merge into one line that ends at a node beside the Sign in button.
// A few coral strands (risk) are stopped at a dotted screening gate; light
// pulses run along the strands, coral ones ending in a small ring flash at
// the gate, clean ones making the node beat. No list names are drawn: the
// page text states the sources for assistive tech.
//
// Purely visual: one <canvas>, hidden below 1000px, aria-hidden. With
// prefers-reduced-motion it draws a single still frame. Pressing Sign in
// quickens the flow and opens the node's ring of ticks outward.
(function () {
  var stage = document.getElementById('si');
  var canvas = document.getElementById('si-strands');
  var btn = document.getElementById('si-btn');
  if (!stage || !canvas || !btn || !canvas.getContext) return;

  var ctx = canvas.getContext('2d');
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var TEAL = [78, 204, 211], CORAL = [255, 122, 105];
  var COUNT = 30, RISK_EVERY = 6, GATE = 0.62;
  function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }
  function smooth(t) { return t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t); }

  // Seeded, so the composition is the same on every visit.
  var seed = 7;
  function rnd() { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }

  var IDLE = { flow: 0.22, pulses: 0.05 }, BUSY = { flow: 0.9, pulses: 0.6 };
  var mix = { flow: IDLE.flow, pulses: IDLE.pulses }, target = IDLE;

  var strands = [];
  for (var i = 0; i < COUNT; i++) {
    var waves = [];
    for (var w = 0; w < 3; w++) waves.push({ f: 1.5 + rnd() * 7, p: rnd() * 6.3, a: 26 + rnd() * 52, s: 0.6 + rnd() * 1.4 });
    strands.push({ u: (i + 0.5) / COUNT + (rnd() - 0.5) * 0.6 / COUNT, risk: i % RISK_EVERY === 3,
      waves: waves, phase: rnd() * 6.283, width: i % 5 ? 1 : 1.6, pulses: [], ring: 0 });
  }

  var W = 0, H = 0, node = { x: 0, y: 0 }, pocket = null, fade = null, riskGrad = null;
  var t = 0, last = 0, beat = 0, pressT = -1, visible = false;

  // The words of the headline, measured from their text (the rows are block
  // elements, so the element boxes would span the whole column).
  function headlineBox() {
    var s = stage.getBoundingClientRect(), box = { l: 1e9, r: -1e9, t: 1e9, b: -1e9 };
    var words = stage.querySelectorAll('.si-w');
    for (var k = 0; k < words.length; k++) {
      var range = document.createRange(); range.selectNodeContents(words[k]);
      var rects = range.getClientRects();
      for (var j = 0; j < rects.length; j++) {
        box.l = Math.min(box.l, rects[j].left - s.left); box.r = Math.max(box.r, rects[j].right - s.left);
        box.t = Math.min(box.t, rects[j].top - s.top); box.b = Math.max(box.b, rects[j].bottom - s.top);
      }
    }
    return box.r > box.l ? { x: box.l - 30, y: box.t - 20, w: box.r - box.l + 60, h: box.b - box.t + 40 } : null;
  }

  function layout() {
    visible = window.innerWidth >= 1000;
    canvas.style.display = visible ? 'block' : 'none';
    if (!visible) return;
    var s = stage.getBoundingClientRect(), b = btn.getBoundingClientRect();
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    W = b.left - s.left; H = s.height;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    node = { x: W - 40, y: b.top - s.top + b.height / 2 };
    pocket = headlineBox();
    fade = ctx.createLinearGradient(0, 0, node.x, 0);
    fade.addColorStop(0, rgba(TEAL, 0.08)); fade.addColorStop(0.6, rgba(TEAL, 0.35)); fade.addColorStop(1, rgba(TEAL, 0.95));
    riskGrad = ctx.createLinearGradient(0, 0, node.x * GATE, 0);
    riskGrad.addColorStop(0, rgba(CORAL, 0.1)); riskGrad.addColorStop(1, rgba(CORAL, 0.9));
  }

  // y of strand st at horizontal fraction x (0..1 of node.x).
  function yAt(st, x) {
    var y0 = H * 0.1 + H * 0.8 * st.u;
    var calm = Math.pow(1 - smooth(x / 0.9), 1.7), n = 0;
    for (var k = 0; k < st.waves.length; k++) { var w = st.waves[k]; n += w.a * Math.sin(w.f * x * 6.283 - t * w.s * mix.flow * 3 + w.p); }
    n *= 0.9 * (0.85 + 0.15 * Math.sin(t * 0.4 + st.phase)) / 2.2;
    return y0 + (node.y - y0) * smooth(x / 0.92) + n * calm;
  }

  function step(dt) {
    mix.flow += (target.flow - mix.flow) * Math.min(1, dt * 2.2);
    mix.pulses += (target.pulses - mix.pulses) * Math.min(1, dt * 2.2);
    t += dt;
    if (pressT >= 0) pressT += dt;
    beat = Math.max(0, beat - dt * 2.5);
    for (var i = 0; i < strands.length; i++) {
      var st = strands[i];
      st.ring = Math.max(0, st.ring - dt * 1.8);
      if (rnd() < mix.pulses * dt) st.pulses.push({ x: 0, v: 0.22 + rnd() * 0.18 + mix.flow * 0.15 });
      var keep = [];
      for (var k = 0; k < st.pulses.length; k++) {
        var p = st.pulses[k]; p.x += p.v * dt;
        if (st.risk && p.x >= GATE) st.ring = 1;
        else if (p.x >= 1) beat = 1;
        else keep.push(p);
      }
      st.pulses = keep;
    }
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    var N = 90;
    for (var i = 0; i < strands.length; i++) {
      var st = strands[i], end = st.risk ? GATE : 1;
      ctx.beginPath();
      for (var k = 0; k <= N; k++) { var x = k / N * end; if (k) ctx.lineTo(x * node.x, yAt(st, x)); else ctx.moveTo(0, yAt(st, 0)); }
      ctx.strokeStyle = st.risk ? riskGrad : fade; ctx.lineWidth = st.risk ? 1.4 : st.width; ctx.stroke();
      for (var q = 0; q < st.pulses.length; q++) {
        var pl = st.pulses[q], vis = smooth((pl.x - 0.18) / 0.25);
        if (vis <= 0) continue;
        var x0 = Math.max(0, pl.x - 0.035);
        ctx.beginPath();
        for (var m = 0; m <= 8; m++) { var px = x0 + (pl.x - x0) * m / 8; if (m) ctx.lineTo(px * node.x, yAt(st, px)); else ctx.moveTo(px * node.x, yAt(st, px)); }
        ctx.globalAlpha = vis; ctx.strokeStyle = st.risk ? rgba(CORAL, 0.95) : 'rgba(214,250,252,.95)';
        ctx.lineWidth = 2.2; ctx.shadowColor = st.risk ? rgba(CORAL, 0.9) : rgba(TEAL, 0.9); ctx.shadowBlur = 10;
        ctx.stroke(); ctx.shadowBlur = 0; ctx.globalAlpha = 1;
      }
      if (st.risk) {
        var ex = GATE * node.x, ey = yAt(st, GATE);
        ctx.beginPath(); ctx.arc(ex, ey, 3, 0, 6.283); ctx.fillStyle = '#04141a'; ctx.fill();
        ctx.strokeStyle = rgba(CORAL, 1); ctx.lineWidth = 1.5; ctx.stroke();
        if (st.ring > 0) { ctx.beginPath(); ctx.arc(ex, ey, 3 + (1 - st.ring) * 16, 0, 6.283); ctx.strokeStyle = rgba(CORAL, st.ring * 0.8); ctx.lineWidth = 1.2; ctx.stroke(); }
      }
    }
    // Keep the headline readable: fade the strands out in a soft pocket around it.
    if (pocket) {
      ctx.save(); ctx.globalCompositeOperation = 'destination-out';
      ctx.translate(pocket.x + pocket.w / 2, pocket.y + pocket.h / 2); ctx.scale(pocket.w * 0.62, pocket.h * 0.78);
      var g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
      g.addColorStop(0, 'rgba(0,0,0,1)'); g.addColorStop(0.62, 'rgba(0,0,0,.92)'); g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, 1, 0, 6.283); ctx.fill(); ctx.restore();
    }
    // The screening gate.
    ctx.save(); ctx.setLineDash([2, 6]); ctx.strokeStyle = rgba(TEAL, 0.28); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(GATE * node.x, node.y - H * 0.2); ctx.lineTo(GATE * node.x, node.y + H * 0.2); ctx.stroke(); ctx.restore();
    // The one line, the node and its ring of ticks (it opens outward on Sign in).
    ctx.shadowColor = rgba(TEAL, 0.9); ctx.shadowBlur = 10 + beat * 14; ctx.strokeStyle = rgba(TEAL, 1); ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(node.x * 0.84, node.y); ctx.lineTo(W, node.y); ctx.stroke(); ctx.shadowBlur = 0;
    var open = pressT >= 0 ? smooth(pressT / 1.1) : 0, gr = 1 + open * 5;
    ctx.save(); ctx.translate(node.x, node.y); ctx.rotate(t * 0.25 + open * 1.5); ctx.globalAlpha = 1 - open * 0.75;
    for (var k2 = 0; k2 < 24; k2++) {
      var a = k2 / 24 * 6.283, r0 = (k2 % 6 ? 11 : 9.5) * gr, r1 = 14 * gr;
      ctx.beginPath(); ctx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); ctx.lineTo(Math.cos(a) * r1, Math.sin(a) * r1);
      ctx.strokeStyle = rgba(TEAL, k2 % 6 ? 0.35 : 0.8); ctx.lineWidth = 1; ctx.stroke();
    }
    ctx.restore();
    ctx.beginPath(); ctx.arc(node.x, node.y, 5 + beat * 2.5, 0, 6.283);
    ctx.fillStyle = '#04141a'; ctx.fill(); ctx.strokeStyle = rgba(TEAL, 1); ctx.lineWidth = 2; ctx.stroke();
  }

  function frame(now) {
    var dt = Math.min(0.05, last ? (now - last) / 1000 : 0); last = now;
    if (visible) { step(dt); draw(); }
    requestAnimationFrame(frame);
  }

  layout();
  if (reduce) { t = 3; if (visible) draw(); }
  else requestAnimationFrame(frame);
  window.addEventListener('resize', function () { layout(); if (reduce && visible) draw(); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { layout(); if (reduce && visible) draw(); });
  // While the server checks the password, the flow quickens.
  var form = btn.form;
  if (form) form.addEventListener('submit', function () { target = BUSY; if (pressT < 0) pressT = 0; });
})();
