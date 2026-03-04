# ADR-010: Ferrofluid Orb Visualizer — Standalone Three.js Experiment

**Status:** Accepted
**Date:** 2026-03-03
**Authors:** Myro Productions

---

## Context

Bob needed a visual representation — something that communicates "alive AI entity" rather than a progress bar or waveform. The goal was a prototype that could be iterated on quickly without coupling to the rest of the Bob pipeline.

The visual needed to:
- React to microphone input in real time
- Express distinct states: idle, listening, thinking, talking
- Look organic, not mechanical

## Decision

Built `experiments/ferrofluid-orb.html` — a single self-contained HTML file using Three.js via CDN importmap. No build step, no bundler, opens directly in a browser.

### Why a single HTML file

The orb is a prototype, not a production UI component. A single file is:
- Zero setup (double-click to open)
- Easy to share and version as a snapshot
- Fast to iterate — edit and reload

The constraint is acceptable for an experiment. If it graduates to production it would be refactored into the dashboard's asset structure.

### Why Three.js via importmap

CDN importmap gives ES module imports (`import * as THREE from 'three'`) without npm or a bundler. Three.js r170 is stable and the importmap pins the exact version, so the file is reproducible without a lockfile.

### Shader approach: vertex displacement + fresnel rim

The orb is a `SphereGeometry` 128×128 with a custom ShaderMaterial.

**Vertex shader:** three layers of 3D simplex noise (`snoise`) at different frequencies and speeds displace vertices outward along their normals. Amplitude is driven by `uEnergy` uniform so the surface breathes in sync with state.

**Fragment shader:** fresnel rim lighting — edge pixels glow brighter toward white. `uColor` lerps between state colors. This gives the "glowing orb" look without any external light sources.

Normals are approximated via finite differences on the displaced position (three extra noise samples per vertex) rather than analytically, which is simpler to implement and adequate at 128×128 resolution.

### State machine

| State | Trigger | Color | Energy |
|---|---|---|---|
| Idle | Default | Deep blue `#0055ff` | 0.15 |
| Listening | Mic RMS above threshold | Blue→green (amplitude) | 0.4–0.9 live |
| Thinking | `T` key | Amber `#ff6600` | 0.6 |
| Talking | `S` key | Green `#00ff88` | 0.7–0.9 pulse |

All transitions lerp over ~0.8s to avoid jarring snaps.

### Web Audio API mic input

`getUserMedia` → `AnalyserNode` → RMS amplitude per frame. Amplitude above ~0.02 normalized threshold triggers listening state and directly modulates `uEnergy`.

### Post-processing

`UnrealBloomPass` adds inner glow. Bloom strength varies by state, making the orb feel more energized when active.

### Environment

- ~2000 random sparkle points in a surrounding sphere (varied size/opacity, slow drift)
- 4 large semi-transparent billboard planes with radial gradient texture form a mist ring around the equator

### Controls panel

Slider UI in a side panel exposes: noise amplitudes (L1/L2/L3), noise speeds, fresnel power, rim color intensity, energy levels per state, bloom strength, and brightness. Export/import allows saving and restoring slider presets as a JSON config embedded in an HTML snapshot.

## Consequences

- Iteration speed is very high — designers can tune the orb without touching any pipeline code.
- The single-file constraint means no module bundling, no TypeScript, no linting. Acceptable for a prototype.
- Three.js CDN dependency means the file requires internet on first load (or a cached copy). Acceptable for internal use.
- The experiment path (`experiments/`) signals that this is not production-ready and subject to redesign.
