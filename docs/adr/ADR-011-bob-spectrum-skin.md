# ADR-011: Bob Spectrum Skin — FFT-Driven Silhouette Ring

**Status:** Accepted
**Date:** 2026-03-03
**Authors:** Myro Productions

---

## Context

The original ferrofluid orb (ADR-010) used constant noise-driven surface displacement that looked alive at rest but didn't communicate anything about Bob's voice. The orb would churn regardless of whether Bob was speaking, silent, or processing.

The redesign goal: make the orb's own skin into a real-time spectrum analyzer. The silhouette of the sphere — the visible edge ring — deforms outward in response to live microphone frequency content. At rest the orb is near-glass smooth. When Bob speaks or hears speech, the ring pulses with the actual spectral shape of the audio.

## Decision

### Camera locked, no orbit

`OrbitControls` removed entirely. Camera fixed at `(0, 0, 3.2)` looking at origin. The spectrum ring only makes visual sense from one viewpoint — if the camera orbits, you'd see deformations that belong to "the far side" of the ring overlapping the near side. A fixed front view makes the clockwise frequency layout legible.

A manual rotation slider (0–360°) was added to let the user set a preferred viewing angle without auto-spin.

### Particles: back hemisphere only

The sparkle particles are filtered at build time to only populate `z < 0` (behind the orb). Front-hemisphere particles occluded Bob's face. The filter uses `phi = Math.acos(-Math.random())` to draw from the back hemisphere uniformly.

### FFT: 2048-point window, 64 log-spaced bands

- `AnalyserNode` `fftSize`: 2048 → frequency resolution ~21.5 Hz/bin at 44.1 kHz
- **64 bands** extracted, logarithmically spaced from **80 Hz to 12 kHz**
  - 80 Hz floor: eliminates DC component and 50/60 Hz power-line hum that caused a persistent spike at the 12 o'clock position
  - 12 kHz ceiling: captures consonant sibilance and presence without including ultrasonic noise
- Log spacing matches how human hearing perceives pitch — an octave at the bass end looks as wide as an octave at the treble end

### GPU delivery: DataTexture (64×1, FloatType)

Frequency amplitudes are uploaded to the GPU each frame as a `THREE.DataTexture`:
- Format: `RedFormat + FloatType` (WebGL2 `R32F`) — one float per band, no packing needed
- Size: 64×1 pixels
- Sampled in the vertex shader as `texture2D(uFreqTex, vec2(bandFrac, 0.5)).r`

This avoids per-vertex JavaScript computation and keeps the spectrum logic entirely on the GPU once the texture is uploaded.

### Asymmetric smoothing

Raw band amplitudes are smoothed with different attack and decay rates:

```
if (raw > current):  new = raw * 0.6 + current * 0.4   (fast attack)
else:                new = raw * 0.15 + current * 0.85  (slow decay)
```

Fast attack preserves transient punch. Slow decay gives a trailing glow effect where peaks persist briefly — this looks more musical and avoids the ring flickering.

### Vertex shader: silhouette deformation

For each vertex:

1. `angle = mod(PI/2 - atan(position.y, position.x), TWO_PI)` — clockwise from +Y (top)
2. `bandFrac = angle / TWO_PI` — maps to texture U coordinate
3. `fAmp = texture2D(uFreqTex, vec2(bandFrac, 0.5)).r * uSpectrumGain * uEnergy * 2.0`
4. `edgeFactor = pow(1.0 - abs(position.z), 3.0)` — maximum at silhouette (z≈0), zero at poles
5. `radialDir = normalize(position.xy)` — outward in the XY plane
6. Displacement: `displaced += vec3(radialDir, 0.0) * fAmp * edgeFactor * 0.5`

The `edgeFactor` cubic falloff concentrates deformation at the visible silhouette ring and suppresses it at the poles. At the poles `position.xy ≈ (0,0)`, so a guard `rxy > 0.001` prevents a zero-division NaN; and `edgeFactor = 0` there anyway, so no visible artifact occurs even without the guard.

Base noise displacement is blended: `noise * uEnergy * (1.0 - edgeFactor * 0.8)` — noise is suppressed where the spectrum is active and restored where it isn't (poles, interior).

### Fragment shader: spectrum glow

Active bands brighten the silhouette additively:

```glsl
float specGlow = vFreqAmp * vEdgeFactor;
col += vec3(0.4, 0.7, 1.0) * specGlow * 0.8;
col += uColor * specGlow * 0.4;
```

The blue-white tint on the first line gives a cool "frequency emission" look. The second line tints with the current state color so the glow changes hue with Bob's state.

### Single `getByteFrequencyData` call per frame

An early bug had both `getMicAmplitude()` and `updateFreqTexture()` independently calling `analyser.getByteFrequencyData(freqData)`. The Web Audio spec does not guarantee these return the same frame — two calls can return different windows. Fixed by:
- `updateFreqTexture()` is called first in `animate()` and populates the shared `freqData` array
- `getMicAmplitude()` reads from `freqData` directly without calling `getByteFrequencyData` again

### Near-glass defaults

| Parameter | Old default | New default |
|---|---|---|
| uN1A (L1 amplitude) | 0.30 | 0.02 |
| uN2A (L2 amplitude) | 0.14 | 0.01 |
| uN3A (L3 amplitude) | 0.06 | 0.005 |
| uBrightness | 0.7 | 0.5 |
| Bloom strength | 1.4 | 1.2 |

The noise is still present — it makes the surface feel alive at rest — but at these amplitudes it's nearly imperceptible and doesn't compete with the spectrum ring.

### Spectrum gain slider

A `uSpectrumGain` uniform scales all band amplitudes before displacement. Exposed as a slider (range 0–3, default 1.0). Persisted in export/import config under `spectrumGain`.

### State machine multiplier

`uEnergy` continues to drive base noise amplitude and also acts as a multiplier on the spectrum ring:
- `idle` → 0.8
- `listening` → 1.0
- `thinking` → 1.2
- `talking` → 1.4

Thinking and talking amplify the ring even when mic input is quiet, giving visual feedback that Bob is active.

## Consequences

- The orb is now a frequency-accurate visualization of whatever audio is active — mic input, playback, or silence.
- Locking the camera removes exploratory interaction. Acceptable because the spectrum ring is the primary value and it requires a fixed viewpoint.
- The 80 Hz floor means sub-bass content (kick drum fundamentals, rumble) is not visualized. This is intentional — sub-bass is rarely present in voice and was a noise source.
- DataTexture upload is one small `Float32Array` (256 bytes) per frame — negligible GPU upload cost.
- The back-hemisphere-only particle constraint means particle count is effectively halved. Visually unnoticeable because particles behind the orb are always visible.
