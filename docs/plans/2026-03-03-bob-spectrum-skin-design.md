# Bob Spectrum Skin — Design

**Date:** 2026-03-03
**Status:** Approved
**Deliverable:** `experiments/ferrofluid-orb.html` (modified in-place)

## What It Is

Replace the constant noise-driven ferrofluid surface with a near-glass sphere whose silhouette ring deforms in response to live microphone frequency analysis. The orb's own skin becomes a clockwise spectrum analyzer — 64 logarithmically-spaced bands from 60 Hz to 8 kHz, wrapping around the sphere's full visible outline.

## Camera & Particles

- OrbitControls removed entirely. Camera locked at `(0, 0, 3.2)` looking at origin.
- Particle buffer filtered at build time: only particles with `z < 0` (behind the orb) are kept. Front hemisphere is empty so nothing occludes Bob.

## Surface Behavior

- Base noise amplitudes (`uN1A`, `uN2A`, `uN3A`) defaulted to ~0.02 — near-glass smooth at rest.
- `uEnergy` state transitions (idle/listening/thinking/talking) remain but primarily drive the spectrum ring amplitude multiplier rather than noise displacement.

## Spectrum Ring

### FFT Setup

- `AnalyserNode` fftSize: **2048** (was 256). Frequency resolution ~21.5 Hz/bin at 44.1 kHz.
- **64 bands** extracted, logarithmically spaced from 60 Hz to 8 kHz.
- Amplitudes uploaded to GPU each frame as a `DataTexture` (64×1, `FloatType`).

### Angle Convention

Clockwise from the top when viewed from the locked front camera:
- Band 0 (60 Hz) → 12 o'clock (north pole)
- Going RIGHT and DOWN → south pole at band 32 (~870 Hz)
- Continuing LEFT and UP → back to 12 o'clock at band 63 (8 kHz)

`angle = atan(position.y, position.x)` in local sphere space. Mapped to band index `floor(angle_normalized * 64)`.

### Vertex Shader Deformation

For each vertex:
1. `angle = atan(position.y, position.x)` — clockwise from +Y axis (top)
2. `bandIndex = int(mod((-angle / TWO_PI + 0.25) * 64.0, 64.0))`
3. `amplitude = texture2D(uFreqTex, vec2((float(bandIndex) + 0.5) / 64.0, 0.5)).r`
4. `edgeFactor = pow(1.0 - abs(position.z), 3.0)` — maximum at silhouette (z≈0), zero at poles
5. Displacement direction: `normalize(vec2(position.x, position.y))` extended to vec3 with z=0
6. Final displacement: `displaced = position + freqDir * amplitude * edgeFactor * uSpectrumGain`

Base noise displacement is blended: `noise * uEnergy * (1.0 - edgeFactor * 0.8)` so noise is suppressed where the spectrum is active.

### Fragment Shader

Active frequency bands brighten the silhouette:
- `spectrumBrightness = texture2D(uFreqTex, ...).r * uSpectrumGain`
- Rim/fresnel colors brightened by `mix(rimColor, vec3(1.0), spectrumBrightness * edgeFactor * 0.6)`

## Visual Defaults

| Parameter | Old default | New default |
|-----------|-------------|-------------|
| uN1A (L1 amplitude) | 0.30 | 0.02 |
| uN2A (L2 amplitude) | 0.14 | 0.01 |
| uN3A (L3 amplitude) | 0.06 | 0.005 |
| uBrightness | 0.7 | 0.5 |
| Bloom strength | 1.4 | 1.2 |

## Controls

New slider in Motion tab → **Blob — Surface** section:
- `sl-sgain` / `v-sgain`: **Spectrum gain** — range 0–3, default 1.0, step 0.05
- Wired to `uSpectrumGain` uniform

## Export/Import

`getConfig()` and `applyConfig()` extended with `spectrumGain` field. No other config changes needed — noise defaults are just different initial values of existing sliders.

## State Machine Integration

`uEnergy` continues to control:
- Base noise amplitude (very low now)
- A multiplier on `uSpectrumGain` per state: idle=0.8, listening=1.0, thinking=1.2, talking=1.4
- Bloom strength target per state (unchanged)
