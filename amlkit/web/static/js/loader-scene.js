// Loading glass, 3D: many strands of light pass a ring and leave the core as one line.
// Loaded on demand by bg-submit.js, only where WebGL works and the screen is wide enough.
// mount() draws into three canvases bg-submit.js has made: the WebGL canvas plus two
// downscaled copies the CSS blurs and screen-blends as bloom (a GPU bloom pass came out
// black on Intel graphics, so the compositor does it).
import * as THREE from '../vendor/three/three.module.js';

const smooth = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const back = (x) => { x = Math.min(1, Math.max(0, x)); const c = 1.5; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2; };

export function mount({ canvas, glowA, glowB, mode, still }) {
  const ONB = mode === 'onboarding';
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
  renderer.setClearColor(0x000000, 1);
  const DPR = Math.min(1.5, devicePixelRatio);
  renderer.setPixelRatio(DPR);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, .1, 100);
  const gA = glowA.getContext('2d'), gB = glowB.getContext('2d');
  const bloom = () => {   // copied right after render, in the same task, so no preserveDrawingBuffer is needed
    gA.clearRect(0, 0, glowA.width, glowA.height); gA.drawImage(canvas, 0, 0, glowA.width, glowA.height);
    gB.clearRect(0, 0, glowB.width, glowB.height); gB.drawImage(glowA, 0, 0, glowB.width, glowB.height);
  };

  let seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647, (seed - 1) / 2147483646);
  const TEAL = new THREE.Color('#4eccd3'), CORAL = new THREE.Color('#ff7a69');
  const START_X = -5.6, GATE_X = ONB ? -1.2 : -.6, CORE_X = ONB ? 2.6 : 2.4;
  const GATE_U = (GATE_X - START_X) / (CORE_X - START_X);
  const glowTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d'), r = x.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(.2, 'rgba(255,255,255,.5)'); r.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = r; x.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c); })();

  // ------------------------------------------------------------ silk: strands of light particles, positions computed on the GPU
  const STRANDS = ONB ? 16 : 38, PER = ONB ? 4200 : 2800, N = STRANDS * PER;
  const aS = new Float32Array(N * 4), aW1 = new Float32Array(N * 4), aW2 = new Float32Array(N * 4), aW3 = new Float32Array(N * 4), aP = new Float32Array(N * 4);
  let BREAK_ID = -1;
  for (let i = 0, n = 0; i < STRANDS; i++) {
    const ang = rnd() * 6.283, r = .5 + rnd() * 2.3, risk = !ONB && i % 7 === 3 ? 1 : 0, phase = i / STRANDS * 6.283;
    if (risk && BREAK_ID < 0) BREAK_ID = i;
    const W = [0, 1, 2].map(() => [1 + rnd() * 3.5, rnd() * 6.3, .25 + rnd() * .45, .5 + rnd()]);
    for (let k = 0; k < PER; k++, n++) {
      aS.set([Math.sin(ang) * r, Math.cos(ang) * r * 1.2, phase, risk + i * 2], n * 4);   // w packs risk (0/1) and strand id
      aW1.set(W[0], n * 4); aW2.set(W[1], n * 4); aW3.set(W[2], n * 4);
      const spark = rnd() < .012 ? 1 : 0;
      aP.set([rnd(), (.035 + rnd() * .03) * (spark ? 2.6 : 1), .6 + rnd() * .9 + spark * 1.6, spark], n * 4);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
  g.setAttribute('aS', new THREE.BufferAttribute(aS, 4)); g.setAttribute('aW1', new THREE.BufferAttribute(aW1, 4));
  g.setAttribute('aW2', new THREE.BufferAttribute(aW2, 4)); g.setAttribute('aW3', new THREE.BufferAttribute(aW3, 4)); g.setAttribute('aP', new THREE.BufferAttribute(aP, 4));
  const U = { uT: { value: 0 }, uFlow: { value: 1 }, uSettle: { value: 0 }, uBuild: { value: 0 }, uBraid: { value: ONB ? 1 : 0 }, uPx: { value: DPR },
    uStart: { value: START_X }, uCore: { value: CORE_X }, uGateU: { value: GATE_U }, uBreakId: { value: BREAK_ID }, uBreak: { value: 0 },
    uTeal: { value: TEAL.clone() }, uCoral: { value: CORAL.clone() } };
  scene.add(Object.assign(new THREE.Points(g, new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: U,
    vertexShader: `
      attribute vec4 aS, aW1, aW2, aW3, aP;
      uniform float uT, uFlow, uSettle, uBuild, uBraid, uPx, uStart, uCore, uGateU, uBreakId, uBreak;
      varying float vA; varying float vRisk; varying float vHot;
      float sm(float x){ x = clamp(x, 0., 1.); return x*x*(3.-2.*x); }
      void main(){
        float risk = mod(aS.w, 2.), id = floor(aS.w / 2.);
        bool breaks = risk > .5 && abs(id - uBreakId) < .5;
        float endU = risk > .5 ? (breaks ? uGateU + (1. - uGateU) * uBreak : uGateU) : 1.;
        float grow = sm((uBuild - .1 - id * .012) / .9);
        float u = fract(aP.x + uT * aP.y) * endU * grow;
        float x = uStart + (uCore - uStart) * u;
        float k = sm(u / .95);
        float calm = pow(max(0., 1. - sm(u / .9)), 1.6) * (1. - uSettle);
        float t = uT * uFlow;
        float ny = aW1.z*sin(aW1.x*u*6.283 - t*aW1.w + aW1.y) + aW2.z*sin(aW2.x*u*6.283 - t*aW2.w + aW2.y) + aW3.z*sin(aW3.x*u*6.283 - t*aW3.w + aW3.y);
        float nz = aW1.z*cos(aW1.x*u*5.1 - t*aW1.w*.8 + aW1.y*1.3) + aW2.z*cos(aW2.x*u*5.1 - t*aW2.w*.8 + aW2.y*1.3) + aW3.z*cos(aW3.x*u*5.1 - t*aW3.w*.8 + aW3.y*1.3);
        float one = 1. - uSettle * (.8 + .2 * u);
        float y = (aS.x * (1. - k) + ny * calm) * one, z = (aS.y * (1. - k) + nz * calm) * one;
        if (uBraid > .5) {
          float R = (.8 + .9 * fract(aS.z * .61)) * pow(max(0., 1. - sm(u / .92)), 1.1) * (1. - uSettle);
          float th = 6.283 * (1.4 * u + 3.2 * u * u) - uT * 1.6 + aS.z;
          y = R * sin(th) + ny * calm * .12; z = R * cos(th) + nz * calm * .12;
        }
        float sc = (fract(sin(aP.x * 91.7) * 4375.5) - .5) * .028 * (1. - u * .8);
        vec4 mv = modelViewMatrix * vec4(x, y + sc, z - sc, 1.);
        gl_Position = projectionMatrix * mv;
        gl_PointSize = aP.z * (1. + 1.4 * u) * (breaks ? 1. + uBreak * .8 : 1.) * uPx * 22. / max(.5, -mv.z);
        vRisk = risk; vHot = aP.w + (breaks ? uBreak * .6 : 0.);
        float edge = risk > .5 && !breaks ? 1. - sm((u / uGateU - .86) / .14) : 1.;
        float fadeRisk = risk > .5 && !breaks ? 1. - uSettle : 1.;
        float tip = grow < 1. ? (1. - grow) * max(0., 1. - (endU * grow - u) / .1) : 0.;
        vA = ((.16 + .5 * pow(max(u, 0.), 1.6)) * clamp(edge, 0., 1.) + tip) * fadeRisk;
      }`,
    fragmentShader: `
      uniform vec3 uTeal, uCoral; varying float vA; varying float vRisk; varying float vHot;
      void main(){
        float d = length(gl_PointCoord - .5) * 2.;
        float a = exp(-d * d * 4.) * max(vA, 0.);
        vec3 c = mix(mix(uTeal, uCoral, vRisk), vec3(1.), clamp(vHot * .7 + vA * .25, 0., 1.));
        gl_FragColor = vec4(c * a * (1. + vHot * 1.2), a);
      }` })), { frustumCulled: false }));

  // ------------------------------------------------------------ the ring: points of light with a faint lens
  const gate = new THREE.Group(); gate.position.x = GATE_X; gate.rotation.y = Math.PI / 2; scene.add(gate);
  const GATE_SCALE = ONB ? .72 : 1;
  const ringU = { uT: { value: 0 }, uPx: { value: DPR }, uC: { value: TEAL.clone() } };
  {
    const M = 5200, aR = new Float32Array(M * 2);
    for (let i = 0; i < M; i++) { aR[i * 2] = rnd() * 6.283; aR[i * 2 + 1] = rnd(); }
    const rg = new THREE.BufferGeometry(); rg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(M * 3), 3)); rg.setAttribute('aR', new THREE.BufferAttribute(aR, 2));
    gate.add(Object.assign(new THREE.Points(rg, new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: ringU,
      vertexShader: `attribute vec2 aR; uniform float uT, uPx; varying float vA;
        void main(){ float a = aR.x + uT * (.05 + aR.y * .08);
          float r = 2.25 + (aR.y - .5) * .07 + sin(aR.x * 40. + uT * 2.) * .012;
          vec4 mv = modelViewMatrix * vec4(cos(a) * r, sin(a) * r, (aR.y - .5) * .05, 1.);
          gl_Position = projectionMatrix * mv; gl_PointSize = (1. + aR.y * 1.6) * uPx * 18. / max(.5, -mv.z);
          vA = .2 + .7 * pow(clamp(.5 + .5 * sin(aR.x * 3. - uT * 1.4), 0., 1.), 10.); }`,
      fragmentShader: `uniform vec3 uC; varying float vA; void main(){ float d = length(gl_PointCoord - .5) * 2.; float a = exp(-d*d*4.) * vA; gl_FragColor = vec4(mix(uC, vec3(1.), .2) * a, a); }` })), { frustumCulled: false }));
  }
  const lensU = { uT: { value: 0 }, uC: { value: TEAL.clone() }, uK: { value: 1 } };
  gate.add(new THREE.Mesh(new THREE.CircleGeometry(2.22, 128), new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: lensU,
    vertexShader: `varying vec2 v; void main(){ v = uv * 2. - 1.; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.); }`,
    fragmentShader: `varying vec2 v; uniform float uT, uK; uniform vec3 uC;
      void main(){ float r = length(v); if (r > 1.) discard;
        float rim = pow(clamp(r, 0., 1.), 14.) * .14;
        float dx = (v.x * .8 + v.y * .6) - (fract(uT * .16) * 3. - 1.5);   // squared by hand: pow() of a negative base is NaN
        float sheet = exp(-dx * dx * 30.) * .035 * (1. - r * r);
        gl_FragColor = vec4(uC * (rim + sheet) * uK, 1.); }` })));
  // crosshair that locks onto the caught strand when the server reports a match
  const reticle = new THREE.Group(); reticle.rotation.y = Math.PI / 2; reticle.visible = false; scene.add(reticle);
  const retMat = () => new THREE.MeshBasicMaterial({ color: CORAL, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
  reticle.add(new THREE.Mesh(new THREE.TorusGeometry(.3, .012, 8, 72), retMat()));
  reticle.add(new THREE.Mesh(new THREE.TorusGeometry(.18, .007, 8, 72), retMat()));
  for (let i = 0; i < 4; i++) { const m = new THREE.Mesh(new THREE.PlaneGeometry(.022, .2), retMat()); const a = i * Math.PI / 2; m.position.set(Math.cos(a) * .46, Math.sin(a) * .46, 0); m.rotation.z = a + Math.PI / 2; reticle.add(m); }

  // ------------------------------------------------------------ the core: a glass orb with a light inside
  const core = new THREE.Group(); core.position.x = CORE_X; scene.add(core);
  const coreU = { uT: { value: 0 }, uC: { value: TEAL.clone() } };
  core.add(new THREE.Mesh(new THREE.SphereGeometry(.46, 64, 64), new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: coreU,
    vertexShader: `varying vec3 vN; varying vec3 vV; varying vec3 vP; void main(){ vN = normalize(normalMatrix * normal); vec4 mv = modelViewMatrix * vec4(position, 1.); vV = normalize(-mv.xyz); vP = position; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `varying vec3 vN; varying vec3 vV; varying vec3 vP; uniform float uT; uniform vec3 uC;
      void main(){ float f = pow(clamp(1. - abs(dot(vN, vV)), 0., 1.), 3.);
        vec3 iri = .5 + .5 * cos(6.283 * (f * .6 + vec3(.0, .33, .67)) + uT * .3);
        float bands = .5 + .5 * sin(vP.y * 18. + uT * 1.2);
        gl_FragColor = vec4(uC * (f * 1.1 + .015) + iri * f * .28 + uC * bands * .02, 1.); }` })));
  const heart = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: '#c9fbff', blending: THREE.AdditiveBlending, depthWrite: false, opacity: .75 })); heart.scale.setScalar(.32); core.add(heart);
  const aura = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: '#4eccd3', blending: THREE.AdditiveBlending, depthWrite: false, opacity: .12 })); aura.scale.setScalar(2.6); core.add(aura);
  const shock = new THREE.Mesh(new THREE.TorusGeometry(1, .01, 8, 128), new THREE.MeshBasicMaterial({ color: TEAL, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  shock.rotation.y = Math.PI / 2; core.add(shock);

  // ------------------------------------------------------------ the one line out: a beam in a soft sheath
  const beamU = { uT: { value: 0 }, uC: { value: TEAL.clone() }, uK: { value: .55 } };
  const BEAM_LEN = 7;
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(.16, .3, BEAM_LEN, 32, 1, true), new THREE.ShaderMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, uniforms: beamU,
    vertexShader: `varying vec2 v; void main(){ v = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.); }`,
    fragmentShader: `varying vec2 v; uniform float uT, uK; uniform vec3 uC;
      void main(){ float across = clamp(1. - abs(v.x * 2. - 1.), 0., 1.);
        float a = (pow(across, 6.) * (1. - v.y) * .9 + pow(across, 1.6) * (1. - v.y) * .06) * (.85 + .15 * sin(v.y * 40. - uT * 6.)) * uK;
        gl_FragColor = vec4(mix(uC, vec3(1.), pow(across, 10.)) * a, a); }` }));
  beam.rotation.z = -Math.PI / 2; scene.add(beam);

  // ------------------------------------------------------------ depth: dust in the volume, bokeh in front
  const softPoints = (count, make, size, opacity) => {
    const pos = new Float32Array(count * 3); for (let i = 0; i < count; i++) pos.set(make(), i * 3);
    const gg = new THREE.BufferGeometry(); gg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const p = new THREE.Points(gg, new THREE.PointsMaterial({ size, map: glowTex, color: '#7fe0e5', transparent: true, opacity, depthWrite: false, blending: THREE.AdditiveBlending })); scene.add(p); return p;
  };
  const dust = softPoints(1400, () => [START_X - 1 + rnd() * 11, (rnd() - .5) * 8, (rnd() - .5) * 7], .03, .35);
  const bokeh = softPoints(28, () => [-3 + rnd() * 8, (rnd() - .5) * 5, 4.5 + rnd() * 3], .9, .07);

  // ------------------------------------------------------------ onboarding: document outlines drift in and dissolve into the braid
  const docs = [];
  if (ONB) {
    const docTex = (title, lines) => { const c = document.createElement('canvas'); c.width = 256; c.height = 330; const x = c.getContext('2d');
      x.strokeStyle = 'rgba(78,204,211,.9)'; x.lineWidth = 2; x.strokeRect(6, 6, 244, 318); x.fillStyle = 'rgba(78,204,211,.06)'; x.fillRect(6, 6, 244, 318);
      x.fillStyle = 'rgba(230,253,255,.9)'; x.font = '600 20px ui-monospace, Menlo, Consolas, monospace'; x.fillText(title, 24, 46);
      x.fillStyle = 'rgba(78,204,211,.5)'; for (let i = 0; i < lines; i++) x.fillRect(24, 78 + i * 28, 110 + ((i * 53) % 90), 6);
      return new THREE.CanvasTexture(c); };
    [['PASSPORT', 6], ['EMIRATES ID', 5], ['TRADE LICENCE', 7], ['OWNERSHIP', 6], ['MOA', 7]].forEach(([title, l], i) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(.95, 1.22), new THREE.MeshBasicMaterial({ map: docTex(title, l), transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
      scene.add(m); docs.push({ m, a: i / 5 * 6.283, r: 2.2 + (i % 2) * .5, y: .9 + (i - 2) * .32, delay: 1.2 + i * 1.0 });
    });
  }

  // ------------------------------------------------------------ timeline
  let t = 0, resolveT = 0, RESOLVE = null, scanT = 0, beatK = 0, raf = 0, last = 0, dead = false;
  const resize = () => { const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false);
    glowA.width = Math.round(w / 4); glowA.height = Math.round(h / 4); glowB.width = Math.round(w / 10); glowB.height = Math.round(h / 10);
    camera.aspect = w / h; camera.updateProjectionMatrix(); };
  addEventListener('resize', resize); resize();
  const tmp = new THREE.Vector3();
  const strandPointCPU = (id, u) => {   // where the caught strand crosses the ring, mirrored from the shader for the crosshair
    const base = id * PER * 4, Sx = aS[base], Sy = aS[base + 1];
    const W = [aW1, aW2, aW3].map((A) => [A[base], A[base + 1], A[base + 2], A[base + 3]]);
    const k = smooth(u / .95), calm = Math.pow(Math.max(0, 1 - smooth(u / .9)), 1.6);
    let ny = 0, nz = 0; for (const w of W) { ny += w[2] * Math.sin(w[0] * u * 6.283 - t * w[3] + w[1]); nz += w[2] * Math.cos(w[0] * u * 5.1 - t * w[3] * .8 + w[1] * 1.3); }
    return tmp.set(START_X + (CORE_X - START_X) * u, Sx * (1 - k) + ny * calm, Sy * (1 - k) + nz * calm);
  };

  function frame(dt) {
    t += dt;
    if (RESOLVE) resolveT = Math.min(1, resolveT + dt * .8);
    U.uT.value = t; U.uBuild.value = t;
    const settle = RESOLVE === 'clear' ? smooth(resolveT) : 0;
    U.uSettle.value = settle;
    U.uBreak.value = RESOLVE === 'match' ? smooth((resolveT - .35) / .55) : 0;
    gate.scale.setScalar(Math.max(.0001, back((t - .35) / .8)) * GATE_SCALE);
    const coreIn = smooth((t - .6) / .8);
    core.scale.setScalar(Math.max(.0001, coreIn) * (1 + beatK * .05 + (RESOLVE ? smooth(resolveT) * .2 : 0)));
    const beamK = smooth((t - 1.1) / .9);
    beam.scale.y = Math.max(.0001, beamK); beam.position.x = CORE_X + BEAM_LEN * beamK / 2;

    // a match: the sweep freezes, the crosshair closes in, the ring turns coral
    const lockK = RESOLVE === 'match' ? smooth(resolveT / .3) : 0;
    if (RESOLVE !== 'match' || resolveT < .05) scanT = t;
    ringU.uT.value = scanT; lensU.uT.value = scanT;
    ringU.uC.value.copy(TEAL).lerp(CORAL, lockK); lensU.uC.value.copy(TEAL).lerp(CORAL, lockK);
    lensU.uK.value = RESOLVE === 'clear' ? 1 - settle * .7 : 1;
    if (RESOLVE === 'match' && BREAK_ID >= 0) {
      reticle.visible = true; reticle.position.copy(strandPointCPU(BREAK_ID, GATE_U));
      reticle.scale.setScalar((1.9 - .9 * lockK) * (1 + .1 * Math.sin(t * 6)));
      reticle.rotation.z = (1 - lockK) * 1.2;
      reticle.children.forEach((m) => { m.material.opacity = lockK * .95; });
    }
    const resCol = RESOLVE === 'match' ? TEAL.clone().lerp(CORAL, smooth((resolveT - .3) / .4)) : TEAL;
    coreU.uC.value.copy(resCol); beamU.uC.value.copy(resCol); aura.material.color.copy(resCol);
    coreU.uT.value = t; beamU.uT.value = t;
    beamU.uK.value = .55 + (RESOLVE === 'clear' ? settle * .6 : 0);
    beatK = Math.pow(.5 + .5 * Math.sin(t * 3.2), 8);
    aura.material.opacity = (.1 + .04 * Math.sin(t * 1.6) + (RESOLVE ? smooth(resolveT) * .1 : 0)) * coreIn;
    heart.material.opacity = .75 * coreIn;
    if (RESOLVE) { const k = (t * .6) % 1; shock.scale.setScalar(.7 + k * 1.6); shock.material.opacity = (1 - k) * .55 * smooth(resolveT); shock.material.color.copy(resCol); }

    for (const d of docs) {
      const life = (((t - d.delay) % 6.5) + 6.5) % 6.5 / 6.5, on = t > d.delay;
      const pull = smooth((life - .45) / .45), a = d.a + t * .35;
      d.m.position.set(-4.4 + Math.cos(a) * .6 + pull * 3.0, d.y * (1 - pull) + Math.sin(a) * .4 * (1 - pull), Math.sin(a) * d.r * (1 - pull));
      d.m.rotation.y = .5 + Math.sin(a) * .4; d.m.scale.setScalar(1 - pull * .6);
      d.m.material.opacity = on ? .8 * smooth(life / .12) * (1 - pull) * (RESOLVE ? 1 - resolveT : 1) : 0;
    }
    dust.rotation.x = t * .01; bokeh.position.x = Math.sin(t * .1) * .6;

    const yaw = -.74 + Math.sin(t * .1) * .12, pitch = .17 + Math.sin(t * .08) * .04, R = 10.6 * (.9 + .1 * smooth(t / 2));
    camera.position.set(Math.sin(yaw) * R - .4, Math.sin(pitch) * R, Math.cos(yaw) * R);
    camera.lookAt(ONB ? -.4 : -.2, 0, 0);
    renderer.render(scene, camera); bloom();
  }

  // Reduced motion: one settled frame, no loop.
  const drawStill = () => { t = 0; for (let i = 0; i < 180; i++) frame(1 / 60); };
  if (still) drawStill();
  else {
    const loop = (now) => { if (dead) return; frame(Math.min(.05, last ? (now - last) / 1000 : 1 / 60)); last = now; raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
  }

  return {
    resolve(verdict) {
      RESOLVE = verdict === 'match' ? 'match' : 'clear';
      if (still) { resolveT = 1; frame(0); }
    },
    destroy() {
      dead = true; cancelAnimationFrame(raf); removeEventListener('resize', resize);
      scene.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } });
      renderer.dispose(); renderer.forceContextLoss();
    },
  };
}
