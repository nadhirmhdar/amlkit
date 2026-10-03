// Sign-in decoration: four strands (each carrying two list sources)
// converge on a node beside the Sign in button. Purely visual and
// static -- it is hidden below 1000px and carries no information the page
// text does not.
(function () {
  var stage = document.getElementById('si');
  var svg = document.getElementById('si-strands');
  var btn = document.getElementById('si-btn');
  if (!stage || !svg || !btn) return;

  var NS = 'http://www.w3.org/2000/svg';
  var SOURCES = ['UN \u00b7 OFAC', 'EU \u00b7 UK', 'UAE \u00b7 FATF', 'PEP \u00b7 Media'];
  var EXTRA = 0;

  function el(name, attrs) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  var drawn = false;
  function draw() {
    if (window.innerWidth < 1000) { svg.style.display = 'none'; return; }
    svg.style.display = 'block';
    var s = stage.getBoundingClientRect();
    var b = btn.getBoundingClientRect();
    var nodeX = Math.round(b.left - s.left - 40);
    var cy = Math.round(b.top - s.top + b.height / 2);
    var H = Math.round(s.height);
    svg.setAttribute('width', nodeX);
    svg.setAttribute('height', H);
    svg.setAttribute('viewBox', '0 0 ' + nodeX + ' ' + H);
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    var defs = el('defs', {});
    var grad = el('linearGradient', { id: 'si-fade', gradientUnits: 'userSpaceOnUse', x1: 0, y1: 0, x2: nodeX, y2: 0 });
    grad.appendChild(el('stop', { offset: '0', 'stop-color': '#4eccd3', 'stop-opacity': '0.10' }));
    grad.appendChild(el('stop', { offset: '0.55', 'stop-color': '#4eccd3', 'stop-opacity': '0.35' }));
    grad.appendChild(el('stop', { offset: '1', 'stop-color': '#4eccd3', 'stop-opacity': '0.9' }));
    defs.appendChild(grad);
    svg.appendChild(defs);
    var paths = [];
    var total = SOURCES.length + EXTRA;
    var pad = Math.round(H * 0.14);
    // Spread labelled sources evenly among the extras.
    var labelAt = {};
    for (var i = 0; i < SOURCES.length; i++) {
      labelAt[Math.round((i + 0.5) * total / SOURCES.length - 0.5)] = SOURCES[i];
    }
    for (var j = 0; j < total; j++) {
      var y = pad + j * (H - 2 * pad) / (total - 1);
      var w = (j % 2 ? -1 : 1) * 40;
      var v = Math.sin(j * 1.7 + 1) * 0.12;
      var d = 'M0 ' + y.toFixed(1) +
        ' C' + (nodeX * (0.30 + v)).toFixed(1) + ' ' + (y + w).toFixed(1) +
        ' ' + (nodeX * (0.58 - v)).toFixed(1) + ' ' + (cy + (y - cy) * 0.18 - w * 0.6).toFixed(1) +
        ' ' + nodeX + ' ' + cy;
      var named = labelAt[j];
      var path = el('path', {
        d: d, fill: 'none', pathLength: 1,
        stroke: named ? '#4eccd3' : 'url(#si-fade)',
        'stroke-opacity': 0.8,
        'stroke-width': 1.6
      });
      svg.appendChild(path);
      paths.push(path);
      if (named) {
        // One source per line so the label fits the left margin.
        var parts = named.split(' \u00b7 ');
        var t = el('text', { x: 14, y: (y - 8 - (parts.length - 1) * 13).toFixed(1) });
        parts.forEach(function (part, k) {
          var ts = el('tspan', { x: 14, dy: k ? 13 : 0 });
          ts.textContent = part;
          t.appendChild(ts);
        });
        svg.appendChild(t);
      }
    }
    svg.appendChild(el('line', { x1: nodeX, y1: cy, x2: nodeX + 40, y2: cy, stroke: '#4eccd3', 'stroke-width': 2 }));
    svg.appendChild(el('circle', { cx: nodeX, cy: cy, r: 5, fill: '#04141a', stroke: '#4eccd3', 'stroke-width': 2 }));
    // Draw the strands in once, staggered, so the convergence reads as an
    // event. Skipped for reduced motion and on redraws after a resize.
    if (!drawn && !(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) {
      paths.forEach(function (p, i) {
        p.style.strokeDasharray = 1;
        p.style.strokeDashoffset = 1;
        p.getBoundingClientRect();
        p.style.transition = 'stroke-dashoffset 1.3s cubic-bezier(.2,.6,.2,1) ' + (i * 25) + 'ms';
        p.style.strokeDashoffset = 0;
      });
    }
    drawn = true;
    svg.style.width = (nodeX + 40) + 'px';
    svg.setAttribute('width', nodeX + 40);
    svg.setAttribute('viewBox', '0 0 ' + (nodeX + 40) + ' ' + H);
  }

  draw();
  window.addEventListener('resize', draw);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);
})();
