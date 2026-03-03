# Bob Spectrum Skin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the ferrofluid orb into a near-glass sphere whose silhouette ring deforms based on live microphone frequency analysis — a clockwise spectrum analyzer (60 Hz–8 kHz, 64 log-spaced bands) embedded in the orb's own skin.

**Architecture:** Single file modification (`experiments/ferrofluid-orb.html`). The vertex shader receives a 64×1 float DataTexture of FFT amplitudes; vertices near the sphere's silhouette (z≈0) are displaced radially outward in XY proportional to their frequency band's amplitude. Camera is locked, front-hemisphere particles are removed, and the base noise amplitude is dropped to near-zero.

**Tech Stack:** Three.js 0.170.0 (ES modules via CDN), Web Audio API AnalyserNode (fftSize 2048), THREE.DataTexture (RedFormat + FloatType), GLSL vertex/fragment shaders.

**Design doc:** `docs/plans/2026-03-03-bob-spectrum-skin-design.md`

---

### Task 1: Lock Camera and Remove Front Particles

**Files:**
- Modify: `experiments/ferrofluid-orb.html`

**Context:**
The file is a single self-contained HTML/JS/GLSL file. OrbitControls are imported from Three.js addons. The particle system is built in an IIFE called `buildParticles()` around line 233. Camera is at `(0, 0, 3.2)` looking at the origin — that's the "locked front view" we want to preserve.

**Step 1: Remove OrbitControls from imports and construction**

Find and delete the OrbitControls import line:
```javascript
// DELETE this line:
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
```

Find and delete the OrbitControls construction block (lines ~199-203):
```javascript
// DELETE these lines:
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 1.8;
controls.maxDistance = 8;
```

Find and delete `controls.update()` inside the `animate()` function:
```javascript
// DELETE this line (inside animate()):
controls.update();
```

**Step 2: Filter particles to back hemisphere only**

Find the particle generation loop inside `buildParticles()`. The current loop generates particles distributed over the full sphere. Replace the `phi` line so particles only land in the back hemisphere (z < 0):

```javascript
// BEFORE (distributes over full sphere):
const phi   = Math.acos(2 * Math.random() - 1);

// AFTER (back hemisphere only — cos(phi) in (-1, 0], so z = r*cos(phi) < 0):
const phi   = Math.acos(-Math.random());
```

This restricts `cos(phi)` to `[-1, 0)`, which maps to the hemisphere where `z < 0`. The particle cloud stays behind the orb when viewed from the front.

**Step 3: Visual check**

Open `experiments/ferrofluid-orb.html` in a browser (must be served via HTTP — e.g. `python3 -m http.server 8080` from the project root, then navigate to `http://localhost:8080/experiments/ferrofluid-orb.html`).

Expected:
- Camera is locked — click-drag does nothing
- Particles only appear behind the orb, none in front
- Orb still renders, bloom still works

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: lock camera, move particles to back hemisphere"
```

---

### Task 2: FFT Infrastructure — DataTexture + Band Bins

**Files:**
- Modify: `experiments/ferrofluid-orb.html`

**Context:**
The existing `AnalyserNode` has `fftSize = 256`, which gives only 128 frequency bins. We need `fftSize = 2048` (1024 bins, ~21.5 Hz/bin at 44100 Hz) for meaningful frequency resolution in the 60 Hz–8 kHz speech range.

We create a 64-element float texture that the vertex shader samples to get frequency amplitude per angular band. This must be created before the `ShaderMaterial` (around line 366) since it's referenced in orbUniforms.

**Step 1: Add spectrum constants and DataTexture before `orbUniforms`**

Find the line `const orbUniforms = {` and insert the following block ABOVE it:

```javascript
// ── Spectrum Analyser ──────────────────────────────────────────────────────
const SPECTRUM_BANDS = 64;
const FREQ_MIN       = 60;
const FREQ_MAX       = 8000;

// 64×1 float texture — updated every frame with FFT amplitudes
const freqTexData = new Float32Array(SPECTRUM_BANDS);
const freqTex = new THREE.DataTexture(
  freqTexData,
  SPECTRUM_BANDS,  // width
  1,               // height
  THREE.RedFormat,
  THREE.FloatType
);
freqTex.minFilter = THREE.LinearFilter;
freqTex.magFilter = THREE.LinearFilter;
freqTex.needsUpdate = true;

// Per-band FFT bin ranges — computed once mic is initialized
let bandBins = null;

function buildBandBins(sampleRate, fftSize) {
  const binHz = sampleRate / fftSize;
  const result = [];
  for (let i = 0; i < SPECTRUM_BANDS; i++) {
    const t0 = i / SPECTRUM_BANDS;
    const t1 = (i + 1) / SPECTRUM_BANDS;
    const f0 = FREQ_MIN * Math.pow(FREQ_MAX / FREQ_MIN, t0);
    const f1 = FREQ_MIN * Math.pow(FREQ_MAX / FREQ_MIN, t1);
    const b0 = Math.max(0, Math.floor(f0 / binHz));
    const b1 = Math.min(fftSize / 2 - 1, Math.ceil(f1 / binHz));
    result.push([b0, Math.max(b0, b1)]);
  }
  return result;
}
```

**Step 2: Add `uFreqTex` and `uSpectrumGain` to `orbUniforms`**

Inside the `orbUniforms` object literal, add two new entries after the existing lighting params:

```javascript
// After uBrightness:
uFreqTex:      { value: freqTex },
uSpectrumGain: { value: 1.0 },
```

**Step 3: Increase fftSize and build band bins in `initMic()`**

Find the line `analyser.fftSize = 256;` inside `initMic()` and replace it:

```javascript
// BEFORE:
analyser.fftSize = 256;
source.connect(analyser);
freqData = new Uint8Array(analyser.frequencyBinCount);

// AFTER:
analyser.fftSize = 2048;
source.connect(analyser);
freqData   = new Uint8Array(analyser.frequencyBinCount);  // 1024 entries
bandBins   = buildBandBins(ctx.sampleRate, analyser.fftSize);
```

**Step 4: Visual check**

Open the file. No visual change expected yet — just confirm the page still loads without console errors. Open DevTools → Console. Should be clean.

**Step 5: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: FFT 2048, DataTexture, log band bins for spectrum ring"
```

---

### Task 3: Vertex Shader — Spectrum Ring Deformation

**Files:**
- Modify: `experiments/ferrofluid-orb.html`

**Context:**
The vertex shader is an ES template literal inside `orbMat = new THREE.ShaderMaterial({...})`. The shader already computes noise-based displacement (`noiseDisp`) and a displaced normal via finite differences. We add spectrum deformation AFTER the normal computation so it doesn't corrupt the lighting normal calculation.

The angle math: `atan(position.y, position.x)` in GLSL returns the angle from the +X axis counterclockwise. We convert to "clockwise from +Y (top)" so that 60 Hz is at the 12 o'clock position.

**Step 1: Add new uniforms and varyings to the vertex shader**

At the TOP of the vertex shader string, after the existing uniforms, add:

```glsl
uniform sampler2D uFreqTex;
uniform float uSpectrumGain;
varying float vFreqAmp;
varying float vEdgeFactor;
```

The full uniform block at the top of the vertex shader should now read:
```glsl
${GLSL_SIMPLEX}
uniform float uTime;
uniform float uEnergy;
uniform float uN1F; uniform float uN1S; uniform float uN1A;
uniform float uN2F; uniform float uN2S; uniform float uN2A;
uniform float uN3F; uniform float uN3S; uniform float uN3A;
uniform sampler2D uFreqTex;
uniform float uSpectrumGain;
varying vec3  vNormal;
varying vec3  vWorldPos;
varying float vDisp;
varying float vFreqAmp;
varying float vEdgeFactor;
```

**Step 2: Add spectrum deformation inside `void main()` of the vertex shader**

Find the line `gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);` near the end of `void main()`.

Insert the following block BEFORE that line:

```glsl
    // ── Spectrum ring deformation ──────────────────────────────────────
    // Clockwise angle from top (+Y axis) in [0, 2PI)
    const float PI     = 3.14159265358979;
    const float TWO_PI = 6.28318530717959;
    float angle = mod(PI * 0.5 - atan(position.y, position.x), TWO_PI);
    float bandFrac = angle / TWO_PI;  // 0=top, 0.25=right, 0.5=bottom, 0.75=left

    // Frequency amplitude for this angular position
    float fAmp = texture2D(uFreqTex, vec2(bandFrac, 0.5)).r * uSpectrumGain * uEnergy * 2.0;

    // Silhouette proximity — max at z≈0 (equatorial ring), zero at poles
    float eFactor = pow(1.0 - abs(position.z), 3.0);

    // Radial outward direction in XY plane (safe against pole singularity)
    float rxy = length(position.xy);
    vec2 radialDir = (rxy > 0.001) ? position.xy / rxy : vec2(0.0);

    // Apply: displace vertices radially outward at their frequency amplitude
    displaced += vec3(radialDir, 0.0) * fAmp * eFactor * 0.5;

    // Pass to fragment shader
    vFreqAmp    = fAmp;
    vEdgeFactor = eFactor;
```

The `0.5` scale factor means a fully-driven band can push the silhouette out by 0.5 units (half the sphere's radius). Adjust this later with the spectrum gain slider if needed.

**Step 3: Visual check**

Open the page. Grant mic access. The orb should still look like a smooth sphere at rest. Speak into the mic — you should start to see the silhouette deform in response (even without the fragment shader update, the geometry will be changing). If nothing happens, check the console for shader compile errors.

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: vertex shader spectrum ring — silhouette deformation from FFT"
```

---

### Task 4: Fragment Shader — Spectrum Glow

**Files:**
- Modify: `experiments/ferrofluid-orb.html`

**Context:**
The fragment shader currently computes `surfaceCol`, `rimColor`, and `col`. We use the passed `vFreqAmp` and `vEdgeFactor` varyings to brighten the rim/glow where active frequency bands are present. This makes active bands visually pop.

**Step 1: Add new uniforms and varyings to the fragment shader**

At the top of the fragment shader string, after the existing uniforms, add:

```glsl
uniform float uSpectrumGain;
varying float vFreqAmp;
varying float vEdgeFactor;
```

**Step 2: Modify the `col` calculation to add spectrum glow**

Find the existing color composition in `void main()` of the fragment shader:

```glsl
      vec3 rimColor = mix(uRimColor, uRimHighColor, fresnel);
      vec3 col      = mix(surfaceCol, rimColor, fresnel * uRimBlend);

      col *= (0.55 + uEnergy * 0.55) * uBrightness;
```

Replace it with:

```glsl
      vec3 rimColor = mix(uRimColor, uRimHighColor, fresnel);
      vec3 col      = mix(surfaceCol, rimColor, fresnel * uRimBlend);

      col *= (0.55 + uEnergy * 0.55) * uBrightness;

      // Spectrum glow — brighten active frequency bands at the silhouette
      float specGlow = vFreqAmp * vEdgeFactor;
      col += vec3(0.4, 0.7, 1.0) * specGlow * 0.8;   // cool blue-white additive
      col += uColor * specGlow * 0.4;                  // tinted by current state color
```

The additive `specGlow` term makes active bands glow bright at the silhouette. The bloom pass will then halo them naturally.

**Step 3: Visual check**

Speak into the mic. Active frequency ranges (vowels are 500 Hz–3 kHz, consonants spike higher) should glow brighter at their corresponding positions on the sphere outline. The ring should feel "alive" to speech. Silence should return the orb to near-dark glass.

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: fragment shader spectrum glow — active bands brighten silhouette"
```

---

### Task 5: Animate Loop — Per-Frame Frequency Update

**Files:**
- Modify: `experiments/ferrofluid-orb.html`

**Context:**
Without writing FFT data into `freqTexData` each frame and setting `freqTex.needsUpdate = true`, the texture stays all-zeros and nothing moves. This task wires the mic data into the GPU every frame.

**Step 1: Add `updateFreqTexture()` function**

Find the `getMicAmplitude()` function (around line 684). Insert the following function directly after it:

```javascript
function updateFreqTexture() {
  if (!analyser || !bandBins) {
    // No mic yet — decay texture to zero
    for (let i = 0; i < SPECTRUM_BANDS; i++) freqTexData[i] *= 0.85;
    freqTex.needsUpdate = true;
    return;
  }
  analyser.getByteFrequencyData(freqData);
  for (let i = 0; i < SPECTRUM_BANDS; i++) {
    const [b0, b1] = bandBins[i];
    let sum = 0;
    for (let b = b0; b <= b1; b++) sum += freqData[b];
    const raw = sum / Math.max(1, b1 - b0 + 1) / 255;
    // Asymmetric smoothing: fast attack, slow decay
    freqTexData[i] = freqTexData[i] < raw
      ? raw * 0.6 + freqTexData[i] * 0.4      // attack
      : raw * 0.15 + freqTexData[i] * 0.85;   // decay
  }
  freqTex.needsUpdate = true;
}
```

**Step 2: Call `updateFreqTexture()` inside `animate()`**

Find the line `orbUniforms.uTime.value = t;` inside `animate()`. Add the call just before it:

```javascript
    updateFreqTexture();
    orbUniforms.uTime.value = t;
```

**Step 3: Visual check**

Speak, clap, or play music near the mic. The spectrum ring should respond with clearly distinct frequency content. Whisper (mostly high-mid) vs. speak low vowels (low-mid) should show noticeably different activation zones on the sphere outline. Silence should smoothly decay.

**Step 4: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: per-frame FFT update feeds spectrum DataTexture"
```

---

### Task 6: Defaults, Spectrum Gain Slider, and Export/Import Update

**Files:**
- Modify: `experiments/ferrofluid-orb.html`

**Context:**
The base noise amplitudes need to drop to near-zero so the orb looks like glass at rest. We also need the spectrum gain slider wired up, and the export/import config functions updated.

**Step 1: Update default noise amplitudes in `orbUniforms`**

Find the noise layer params in `orbUniforms`:
```javascript
uN1F: { value: 1.8 }, uN1S: { value: 0.40 }, uN1A: { value: 0.30 },
uN2F: { value: 3.5 }, uN2S: { value: 0.70 }, uN2A: { value: 0.14 },
uN3F: { value: 7.0 }, uN3S: { value: 1.10 }, uN3A: { value: 0.06 },
```

Replace with:
```javascript
uN1F: { value: 1.8 }, uN1S: { value: 0.40 }, uN1A: { value: 0.02 },
uN2F: { value: 3.5 }, uN2S: { value: 0.70 }, uN2A: { value: 0.01 },
uN3F: { value: 7.0 }, uN3S: { value: 1.10 }, uN3A: { value: 0.005 },
```

Also update `uBrightness`:
```javascript
// BEFORE:
uBrightness: { value: 0.7 },
// AFTER:
uBrightness: { value: 0.5 },
```

**Step 2: Update the HTML slider defaults to match**

Find the three amplitude slider HTML elements and update their `value` attributes and `<span>` text:

```html
<!-- BEFORE: -->
<div class="sl-row"><div class="sl-head"><label>L1 amplitude</label><span id="v-n1a">0.30</span></div><input type="range" id="sl-n1a" min="0"  max="2.0" step="0.01" value="0.30"></div>
<div class="sl-row"><div class="sl-head"><label>L2 amplitude</label><span id="v-n2a">0.14</span></div><input type="range" id="sl-n2a" min="0"  max="1.2" step="0.01" value="0.14"></div>
<div class="sl-row"><div class="sl-head"><label>L3 amplitude</label><span id="v-n3a">0.06</span></div><input type="range" id="sl-n3a" min="0"  max="0.6" step="0.01" value="0.06"></div>

<!-- AFTER: -->
<div class="sl-row"><div class="sl-head"><label>L1 amplitude</label><span id="v-n1a">0.02</span></div><input type="range" id="sl-n1a" min="0"  max="2.0" step="0.01" value="0.02"></div>
<div class="sl-row"><div class="sl-head"><label>L2 amplitude</label><span id="v-n2a">0.01</span></div><input type="range" id="sl-n2a" min="0"  max="1.2" step="0.01" value="0.01"></div>
<div class="sl-row"><div class="sl-head"><label>L3 amplitude</label><span id="v-n3a">0.005</span></div><input type="range" id="sl-n3a" min="0"  max="0.6" step="0.01" value="0.005"></div>
```

Also update the brightness slider:
```html
<!-- BEFORE: -->
<div class="sl-row"><div class="sl-head"><label>Brightness</label>  <span id="v-brit">0.7</span></div><input type="range" id="sl-brit"  min="0"   max="2"   step="0.02" value="0.7"></div>

<!-- AFTER: -->
<div class="sl-row"><div class="sl-head"><label>Brightness</label>  <span id="v-brit">0.5</span></div><input type="range" id="sl-brit"  min="0"   max="2"   step="0.02" value="0.5"></div>
```

**Step 3: Add the Spectrum Gain slider to Motion tab HTML**

Find the `<div class="cp-section">Blob — Surface</div>` header in the Motion tab. Add the spectrum gain slider as the FIRST item in that section, right after the section header:

```html
<div class="cp-section">Blob — Surface</div>
<div class="sl-row"><div class="sl-head"><label>Spectrum gain</label><span id="v-sgain">1.00</span></div><input type="range" id="sl-sgain" min="0" max="3" step="0.05" value="1.0"></div>
```

**Step 4: Wire the slider in JS**

Find the blob surface sliders section in the JS (near `sl('sl-n1f', ...)`). Add the spectrum gain line first:

```javascript
// Blob surface sliders
sl('sl-sgain', 'v-sgain', v => orbUniforms.uSpectrumGain.value = v);
sl('sl-n1f', 'v-n1f', v => orbUniforms.uN1F.value = v);
// ... rest unchanged
```

**Step 5: Update `getConfig()` and `applyConfig()`**

In `getConfig()`, add `spectrumGain` to the return object:
```javascript
// After the existing fields, before the closing brace:
spectrumGain: orbUniforms.uSpectrumGain.value,
```

In `applyConfig()`, add spectrum gain to the `nums` array:
```javascript
['sl-sgain', 'spectrumGain', v => orbUniforms.uSpectrumGain.value = v],
```

**Step 6: Visual check**

Open the page. The orb should now look nearly glass-smooth at rest (tiny shimmer from minimal noise). Speaking should activate the spectrum ring clearly. The Spectrum gain slider (Motion → Blob Surface section, top) should scale the ring response. Exporting and reimporting a template should restore the spectrum gain value.

**Step 7: Commit**

```bash
git add experiments/ferrofluid-orb.html
git commit -m "feat: near-glass defaults, spectrum gain slider, export/import update"
```

---

## Summary

After all 6 tasks:
- Camera is locked front-facing, no orbit
- Particles only behind the orb
- Near-glass surface at rest (noise ≈ 0)
- 64 log-spaced frequency bands (60 Hz–8 kHz) deform the silhouette ring clockwise from top
- Active bands glow bright blue-white via additive fragment color
- Spectrum gain slider in Motion → Blob Surface section
- Export/import preserves all new settings
