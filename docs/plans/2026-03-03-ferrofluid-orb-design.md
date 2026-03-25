# Ferrofluid Orb Visualizer — Design

**Date:** 2026-03-03
**Status:** Approved
**Deliverable:** `experiments/ferrofluid-orb.html`

## What It Is

A standalone Three.js ferrofluid orb — a living visual representation of an AI entity. Reacts to mic input and keyboard-driven state changes. Prototype only; no Bob pipeline integration yet.

## Architecture

Single self-contained HTML file. Three.js via CDN importmap. No build step, open directly in browser.

## Scene

- Background: near-black void with slight blue tint (`#050810`)
- Perspective camera with OrbitControls (click-drag to rotate)
- UnrealBloomPass post-processing for inner glow

## The Orb

- `SphereGeometry` 128x128 subdivisions
- **Vertex shader:** three layers of 3D simplex noise at different frequencies/speeds, displacing vertices along their normals. Displacement amplitude driven by `uEnergy` uniform.
- **Fragment shader:** fresnel rim lighting + `uColor` uniform that lerps between state colors. Edges glow brighter toward white.

## State Machine

| State     | Trigger              | Color              | Energy       |
|-----------|----------------------|--------------------|--------------|
| Idle      | Default              | Deep blue `#0055ff`| 0.15         |
| Listening | Mic above threshold  | Blue→green (amp)   | 0.4–0.9 live |
| Thinking  | `T` key              | Amber `#ff6600`    | 0.6          |
| Talking   | `S` key              | Green `#00ff88`    | 0.7–0.9 pulse|

All state color/energy transitions lerp over ~0.8s.

## Mic Input

Web Audio API `getUserMedia` → `AnalyserNode`. RMS amplitude calculated each frame. Above ~0.02 normalized threshold = listening. Amplitude directly modulates `uEnergy`.

## Environment

- **Sparkly void:** ~2000 random points in a surrounding sphere, slowly drifting. Varied size/opacity.
- **Mist ring:** a few large semi-transparent billboard planes with radial gradient texture around the orb's equator. Opacity ~0.08.

## Controls

| Key | Action            |
|-----|-------------------|
| T   | Thinking state    |
| S   | Talking state     |
| I   | Return to idle    |
| Mic | Auto-listening    |

Click + drag: orbit camera.
