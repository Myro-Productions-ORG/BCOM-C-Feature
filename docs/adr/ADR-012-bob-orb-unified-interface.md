# ADR-012: Bob Orb — Unified Interface

**Date:** 2026-03-04
**Status:** Accepted

## Context

The Bob voice pipeline previously required two separate browser tabs to operate:
- `experiments/ferrofluid-orb.html` — the Three.js ferrofluid visualizer (standalone prototype)
- `src/process-manager/app.py` served at `http://localhost:7766` — service management dashboard with log terminals, settings panel, and start/stop controls

This split created operational friction: the operator needed to navigate between pages to start services, monitor logs, and adjust LLM or TTS parameters. The orb was also not wired to actual pipeline state — it only responded to keyboard shortcuts (T/S/I) for manual testing.

## Decision

Transform `experiments/ferrofluid-orb.html` into the single Bob interface. The Three.js canvas stays fullscreen. All controls live as glassmorphism overlay panels (`position: fixed`, `backdrop-filter: blur(14px)`, 40% opacity) on top of the orb.

**Layout:**
- Top bar (48px, fixed): state dot + "BOB" brand, master START/STOP button, STT/ORC/CLI service pills
- Terminal panel (bottom-left, 42vw × 26vh): three tabbed log streams — STT, ORC, CLI — via SSE from process-manager
- Settings drawer (bottom-right, 280px, slide-up): voice selector, mic device, model, temperature, max tokens, apply, clear memory

**Backend wiring:**
- All service management calls route to the existing process-manager API at `http://127.0.0.1:7766`
- Orb state machine (idle/listening/thinking/talking) driven by `ws://127.0.0.1:8766/ws/control` — the orchestrator's existing broadcast WebSocket
- Voice selection (`POST /api/settings` with `voice_id`) added to the orchestrator's `SettingsUpdate` model; takes effect on next TTS call, no restart needed

**Voice roster (ElevenLabs standard voices):**
Default voice `27ugurx8r230xq5a0vKV` preserved. Seven additional voices available: Adam, Josh, Arnold (American male), Domi, Elli, Rachel (American female), Fin (Irish male).

**Implementation approach:** Non-module `<script>` block appended to the existing file. Module-scoped `setState` exposed on `window._bobSetState` to allow the overlay script to drive orb visuals. State name `'speaking'` mapped to orb key `'talking'` to match the existing STATES object.

## Consequences

- Single page to open — operator navigates to `experiments/ferrofluid-orb.html` only
- Orb visually reflects real pipeline state (idle → listening → thinking → talking) without any manual keyboard input
- Existing CONTROLS panel (top-right, tabbed shader sliders) remains fully accessible
- process-manager must be running at port 7766 for service management to work (unchanged requirement)
- `experiments/` directory name no longer reflects the file's role; renaming deferred to avoid breaking Caddy paths
