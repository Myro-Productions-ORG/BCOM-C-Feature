# Ferrofluid Orb Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone Three.js ferrofluid orb visualizer that reacts to mic input and keyboard-driven AI state changes.

**Architecture:** Single self-contained HTML file using Three.js ES modules via CDN importmap. Vertex displacement shader on a high-subdivision sphere creates the ferrofluid surface. Web Audio API drives real-time mic amplitude. A simple state machine maps idle/listening/thinking/talking states to color and energy uniforms.

**Tech Stack:** Three.js 0.170.0 (CDN), GLSL (inline shaders), Web Audio API, no build step.

---

### Task 1: HTML skeleton + Three.js scene

**Files:**
- Create: `experiments/ferrofluid-orb.html`

**Step 1: Create the file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ferrofluid Orb</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: #050810; overflow: hidden; }
    canvas { display: block; }
    #status {
      position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
      color: rgba(255,255,255,0.25); font-family: 'Courier New', monospace;
      font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase;
      pointer-events: none;
    }
  </style>
</head>
<body>
<div id="status">idle — T: think · S: speak · I: idle</div>

<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/"
  }
}
</script>

<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

// ── Scene ───────────────────────────────────────────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x050810);

const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 100);
camera.position.set(0, 0, 3.2);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 1.8;
controls.maxDistance = 8;

// ── Post-processing ─────────────────────────────────────────────────────────
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(innerWidth, innerHeight),
  1.4,   // strength
  0.4,   // radius
  0.1    // threshold
);
composer.addPass(bloomPass);

// ── Resize ──────────────────────────────────────────────────────────────────
window.addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  composer.setSize(innerWidth, innerHeight);
});

// ── Clock & animate ──────────────────────────────────────────────────────────
const clock = new THREE.Clock();

function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  controls.update();
  composer.render();
}
animate();

</script>
</body>
</html>
```

**Step 2: Verify**

Open `experiments/ferrofluid-orb.html` directly in Chrome or Firefox.
Expected: solid near-black void (`#050810`), no errors in DevTools console, subtle status text at bottom.

**Step 3: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: ferrofluid orb — scene skeleton + bloom"
```

---

### Task 2: Sparkly void particles

**Files:**
- Modify: `experiments/ferrofluid-orb.html` — add particle system before the `animate()` call

**Step 1: Add particle geometry**

Inside the `<script type="module">` block, after the clock declaration and before `animate()`, add:

```javascript
// ── Particles (sparkly void) ─────────────────────────────────────────────────
(function buildParticles() {
  const COUNT = 2200;
  const positions = new Float32Array(COUNT * 3);
  const sizes     = new Float32Array(COUNT);
  const alphas    = new Float32Array(COUNT);

  for (let i = 0; i < COUNT; i++) {
    // distribute in a shell between r=2.5 and r=7
    const r     = 2.5 + Math.random() * 4.5;
    const theta = Math.random() * Math.PI * 2;
    const phi   = Math.acos(2 * Math.random() - 1);
    positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
    sizes[i]  = 0.5 + Math.random() * 1.5;
    alphas[i] = 0.2 + Math.random() * 0.7;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('aSize',    new THREE.BufferAttribute(sizes, 1));
  geo.setAttribute('aAlpha',   new THREE.BufferAttribute(alphas, 1));

  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    vertexShader: `
      attribute float aSize;
      attribute float aAlpha;
      varying float vAlpha;
      void main() {
        vAlpha = aAlpha;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = aSize * (300.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: `
      varying float vAlpha;
      void main() {
        float d = length(gl_PointCoord - 0.5);
        if (d > 0.5) discard;
        float a = smoothstep(0.5, 0.1, d) * vAlpha;
        gl_FragColor = vec4(0.7, 0.85, 1.0, a);
      }
    `,
  });

  scene.add(new THREE.Points(geo, mat));
})();
```

**Step 2: Add gentle drift in animate()**

Replace the animate function body with:

```javascript
function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  controls.update();

  // slow particle drift — rotate around Y very slightly
  scene.children.forEach(child => {
    if (child.isPoints) {
      child.rotation.y = t * 0.012;
      child.rotation.x = t * 0.005;
    }
  });

  composer.render();
}
```

**Step 3: Verify**

Reload the file. Expected: 2000+ tiny blue-white stars scattered in a sphere around the camera, slowly rotating. No orb yet.

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: ferrofluid orb — sparkly void particles"
```

---

### Task 3: GLSL simplex noise + ferrofluid orb shader

This is the core task. The orb uses a custom ShaderMaterial. The vertex shader displaces sphere vertices using layered 3D simplex noise. The fragment shader handles color and fresnel glow.

**Files:**
- Modify: `experiments/ferrofluid-orb.html` — add orb after particles, wire uniforms into animate()

**Step 1: Add the orb**

After the particle IIFE and before `animate()`, add:

```javascript
// ── Ferrofluid Orb ───────────────────────────────────────────────────────────
const GLSL_SIMPLEX = /* glsl */`
  vec3 mod289v3(vec3 x) { return x - floor(x*(1./289.))*289.; }
  vec4 mod289v4(vec4 x) { return x - floor(x*(1./289.))*289.; }
  vec4 permute(vec4 x) { return mod289v4(((x*34.)+1.)*x); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314*r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1./6., 1./3.);
    const vec4 D = vec4(0., 0.5, 1., 2.);
    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g  = step(x0.yzx, x0.xyz);
    vec3 l  = 1. - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289v3(i);
    vec4 p = permute(permute(permute(
      i.z + vec4(0., i1.z, i2.z, 1.))
      + i.y + vec4(0., i1.y, i2.y, 1.))
      + i.x + vec4(0., i1.x, i2.x, 1.));
    float n_ = .142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.*floor(p*ns.z*ns.z);
    vec4 x_ = floor(j*ns.z);
    vec4 y_ = floor(j - 7.*x_);
    vec4 x = x_*ns.x + ns.yyyy;
    vec4 y = y_*ns.x + ns.yyyy;
    vec4 h = 1. - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0)*2.+1.;
    vec4 s1 = floor(b1)*2.+1.;
    vec4 sh = -step(h, vec4(0.));
    vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;
    vec3 p0 = vec3(a0.xy,h.x);
    vec3 p1 = vec3(a0.zw,h.y);
    vec3 p2 = vec3(a1.xy,h.z);
    vec3 p3 = vec3(a1.zw,h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
    p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
    vec4 m = max(.6 - vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)), 0.);
    m = m*m;
    return 42.*dot(m*m, vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
  }
`;

const orbUniforms = {
  uTime:   { value: 0 },
  uEnergy: { value: 0.15 },
  uColor:  { value: new THREE.Color(0x0055ff) },
};

const orbMat = new THREE.ShaderMaterial({
  uniforms: orbUniforms,
  vertexShader: /* glsl */`
    ${GLSL_SIMPLEX}
    uniform float uTime;
    uniform float uEnergy;
    varying vec3 vNormal;
    varying vec3 vWorldPos;

    void main() {
      vec3 p = position;

      // Three layers of noise at increasing frequency and speed
      float n1 = snoise(p * 1.8 + uTime * 0.40) * 0.30;
      float n2 = snoise(p * 3.5 + uTime * 0.70) * 0.14;
      float n3 = snoise(p * 7.0 + uTime * 1.10) * 0.06;
      float disp = (n1 + n2 + n3) * uEnergy;

      vec3 displaced = p + normal * disp;

      vNormal   = normalize(normalMatrix * normal);
      vWorldPos = (modelMatrix * vec4(displaced, 1.0)).xyz;

      gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
    }
  `,
  fragmentShader: /* glsl */`
    uniform vec3  uColor;
    uniform float uEnergy;
    varying vec3  vNormal;
    varying vec3  vWorldPos;

    void main() {
      vec3 viewDir  = normalize(cameraPosition - vWorldPos);
      float fresnel = pow(1.0 - max(dot(vNormal, viewDir), 0.0), 3.0);

      // Core color blends toward bright tinted-white at the rim
      vec3 rimColor = mix(uColor * 2.0, vec3(1.0), 0.4);
      vec3 col = mix(uColor * 0.6, rimColor, fresnel);

      // Subtle iridescent shimmer based on normal
      col += vec3(0.0, 0.02, 0.08) * (1.0 - fresnel) * uEnergy;

      // Overall brightness scales with energy
      col *= 0.8 + uEnergy * 0.6;

      gl_FragColor = vec4(col, 1.0);
    }
  `,
});

const orbGeo  = new THREE.SphereGeometry(1, 128, 128);
const orbMesh = new THREE.Mesh(orbGeo, orbMat);
scene.add(orbMesh);
```

**Step 2: Update uniforms in animate()**

Replace the animate function:

```javascript
function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  controls.update();

  scene.children.forEach(child => {
    if (child.isPoints) {
      child.rotation.y = t * 0.012;
      child.rotation.x = t * 0.005;
    }
  });

  orbUniforms.uTime.value = t;

  composer.render();
}
```

**Step 3: Verify**

Reload. Expected: an animated blue blobby orb — lumpy, spiked, constantly morphing — glowing against the star field. Fresnel makes edges brighter.

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: ferrofluid orb — vertex displacement shader + fresnel"
```

---

### Task 4: Mist ring

Semi-transparent fog planes around the orb's equator give depth and mystery.

**Files:**
- Modify: `experiments/ferrofluid-orb.html` — add mist after the orb mesh

**Step 1: Add mist planes**

After `scene.add(orbMesh)`, add:

```javascript
// ── Mist Ring ────────────────────────────────────────────────────────────────
(function buildMist() {
  // Build a radial gradient texture via canvas
  const size = 256;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const g = ctx.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
  g.addColorStop(0.0, 'rgba(30, 80, 180, 0.18)');
  g.addColorStop(0.4, 'rgba(20, 60, 160, 0.08)');
  g.addColorStop(1.0, 'rgba(0,  0,   0,  0.00)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(canvas);

  const mistMat = new THREE.MeshBasicMaterial({
    map: tex,
    transparent: true,
    opacity: 1,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });

  // 4 planes, rotated around the orb
  for (let i = 0; i < 4; i++) {
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(3.8, 3.8), mistMat);
    plane.rotation.x = Math.PI / 2;
    plane.rotation.z = (i / 4) * Math.PI;
    plane.position.y = -0.05 + (Math.random() - 0.5) * 0.3;
    scene.add(plane);
  }
})();
```

**Step 2: Verify**

Reload. Expected: a soft, diffuse blue-indigo glow around the orb's equator — looks like digital mist or plasma fog. Should be subtle (not dominant).

**Step 3: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: ferrofluid orb — mist ring"
```

---

### Task 5: State machine + keyboard controls

**Files:**
- Modify: `experiments/ferrofluid-orb.html` — add state machine before animate(), wire into animate()

**Step 1: Add state machine**

After the mist IIFE and before `animate()`, add:

```javascript
// ── State Machine ────────────────────────────────────────────────────────────
const STATES = {
  idle:      { color: new THREE.Color(0x0044dd), energy: 0.15, bloomStr: 1.1 },
  listening: { color: new THREE.Color(0x0099ff), energy: 0.50, bloomStr: 1.4 },
  thinking:  { color: new THREE.Color(0xff6600), energy: 0.62, bloomStr: 1.6 },
  talking:   { color: new THREE.Color(0x00ff88), energy: 0.78, bloomStr: 1.8 },
};

let state       = 'idle';
let targetColor  = STATES.idle.color.clone();
let targetEnergy = STATES.idle.energy;
let targetBloom  = STATES.idle.bloomStr;
const lerpColor  = new THREE.Color(0x0044dd);

function setState(name) {
  if (!STATES[name]) return;
  state = name;
  targetColor.copy(STATES[name].color);
  targetEnergy = STATES[name].energy;
  targetBloom  = STATES[name].bloomStr;
  document.getElementById('status').textContent =
    name === 'idle'      ? 'idle — T: think · S: speak · I: idle' :
    name === 'listening' ? 'listening...' :
    name === 'thinking'  ? 'thinking...' :
                           'speaking...';
}

window.addEventListener('keydown', (e) => {
  const k = e.key.toLowerCase();
  if (k === 't') setState('thinking');
  if (k === 's') setState('talking');
  if (k === 'i') setState('idle');
});
```

**Step 2: Wire lerp into animate()**

Replace animate() with:

```javascript
const LERP_SPEED = 0.025; // ~0.8s transition at 60fps

function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  controls.update();

  // Particle drift
  scene.children.forEach(child => {
    if (child.isPoints) {
      child.rotation.y = t * 0.012;
      child.rotation.x = t * 0.005;
    }
  });

  // Talking: simulate pulsing energy
  let energyTarget = targetEnergy;
  if (state === 'talking') {
    energyTarget = targetEnergy + Math.sin(t * 7.0) * 0.12;
  }
  if (state === 'thinking') {
    energyTarget = targetEnergy + Math.sin(t * 2.5) * 0.08;
  }

  // Lerp orb uniforms
  orbUniforms.uEnergy.value += (energyTarget - orbUniforms.uEnergy.value) * LERP_SPEED * 3;
  lerpColor.lerp(targetColor, LERP_SPEED * 2);
  orbUniforms.uColor.value.copy(lerpColor);
  orbUniforms.uTime.value = t;

  // Lerp bloom
  bloomPass.strength += (targetBloom - bloomPass.strength) * LERP_SPEED * 2;

  composer.render();
}
```

**Step 3: Verify**

Reload. Press T — orb should slowly shift to amber-orange with more agitation. Press S — shifts to green with pulsing. Press I — returns to blue calm. All transitions should be smooth (~0.5-1s), not instant.

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: ferrofluid orb — state machine + keyboard controls"
```

---

### Task 6: Web Audio API — live mic input

**Files:**
- Modify: `experiments/ferrofluid-orb.html` — add mic setup after state machine, update animate()

**Step 1: Add mic setup**

After the keyboard listener, add:

```javascript
// ── Mic Input ────────────────────────────────────────────────────────────────
let analyser   = null;
let freqData   = null;
let micActive  = false;
const MIC_THRESHOLD = 0.018; // normalized RMS — tune to taste
const MIC_SILENCE_FRAMES = 45; // frames of quiet before returning to idle
let silenceFrames = 0;

async function initMic() {
  try {
    const stream  = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    const ctx     = new AudioContext();
    const source  = ctx.createMediaStreamSource(stream);
    analyser      = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    freqData = new Uint8Array(analyser.frequencyBinCount);
    micActive = true;
    console.log('[orb] mic initialized');
  } catch (err) {
    console.warn('[orb] mic not available:', err.message);
  }
}

function getMicAmplitude() {
  if (!analyser) return 0;
  analyser.getByteFrequencyData(freqData);
  let sum = 0;
  for (let i = 0; i < freqData.length; i++) sum += freqData[i] * freqData[i];
  return Math.sqrt(sum / freqData.length) / 255; // 0..1
}

initMic();
```

**Step 2: Wire mic into animate()**

At the top of animate(), before the particle drift block, add:

```javascript
  // Mic amplitude → listening state
  if (micActive && (state === 'idle' || state === 'listening')) {
    const amp = getMicAmplitude();
    if (amp > MIC_THRESHOLD) {
      silenceFrames = 0;
      if (state !== 'listening') setState('listening');
      // Drive energy directly from mic amplitude — map 0..0.2 → 0.3..0.95
      targetEnergy = 0.30 + Math.min(amp / 0.2, 1.0) * 0.65;
      // Shift color toward green as amplitude increases
      const greenAmount = Math.min(amp / 0.15, 1.0);
      targetColor.setRGB(
        0.0 * (1 - greenAmount) + 0.0 * greenAmount,
        0.6 * (1 - greenAmount) + 1.0 * greenAmount,
        1.0 * (1 - greenAmount) + 0.53 * greenAmount,
      );
    } else {
      silenceFrames++;
      if (state === 'listening' && silenceFrames > MIC_SILENCE_FRAMES) {
        setState('idle');
      }
    }
  }
```

**Step 3: Verify**

Reload. Browser will prompt for mic permission — allow it. Speak or clap near mic. Expected: orb shifts to listening state, pulses with your voice amplitude, color drifts toward green as you get louder, settles back to idle ~0.75s after silence.

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: ferrofluid orb — live mic input via Web Audio API"
```

---

### Task 7: Final polish

Small finishing touches that make it feel premium.

**Files:**
- Modify: `experiments/ferrofluid-orb.html`

**Step 1: Add a faint ambient point light**

After `scene.add(orbMesh)`, add:

```javascript
// Subtle fill light so particles catch a little warmth
const ambient = new THREE.AmbientLight(0x0a1530, 0.4);
scene.add(ambient);
```

**Step 2: Add a slow idle sway to the orb**

In animate(), after the lerp block and before `composer.render()`, add:

```javascript
  // Slow gentle sway at idle
  const idleAmt = state === 'idle' ? 1.0 : 0.15;
  orbMesh.rotation.y = t * 0.08 * idleAmt;
  orbMesh.rotation.x = Math.sin(t * 0.13) * 0.04 * idleAmt;
```

**Step 3: Add a thinking rotation**

In the same block, add after the sway lines:

```javascript
  if (state === 'thinking') {
    orbMesh.rotation.y = t * 0.35;
  }
```

**Step 4: Tune bloom per-state more subtly**

The bloom threshold can be adjusted to taste in the UnrealBloomPass constructor:
- `strength: 1.4` (already set)
- `radius: 0.4`
- `threshold: 0.1`

If the bloom feels too heavy, reduce strength to `1.0`. If too subtle, raise to `1.8`.

**Step 5: Verify the complete experience**

Walk through this checklist:
- [ ] Opens in browser with no console errors
- [ ] Dark void with sparkly stars visible
- [ ] Blue orb gently morphing at idle
- [ ] Press T — smooth orange shift, more agitation, orb rotates faster
- [ ] Press S — smooth green shift, pulsing energy
- [ ] Press I — returns to calm blue
- [ ] Speak near mic — orb responds in real time, colors shift blue→green with voice strength
- [ ] Silence for 1s — orb settles back to idle
- [ ] Click-drag rotates camera around orb
- [ ] Status text updates with state changes

**Step 6: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: ferrofluid orb — polish, sway, thinking rotation"
```

---

## Notes

- The `MIC_THRESHOLD` constant (0.018) may need tuning based on mic sensitivity. If the orb triggers listening without speech, raise it to 0.03.
- Three.js 0.170.0 is pinned via CDN. If bumping versions, verify `UnrealBloomPass` import path hasn't changed.
- This file has no external dependencies beyond the CDN. Works offline if Three.js is cached.
- Future integration point: replace keyboard state triggers with WebSocket messages from Bob pipeline (Phase 2+).
