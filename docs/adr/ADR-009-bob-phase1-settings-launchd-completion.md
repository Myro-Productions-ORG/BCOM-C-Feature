# ADR-009: Bob Phase 1 Completion — Settings Panel, Live Runtime Config, and launchd Persistence

**Status:** Accepted
**Date:** 2026-03-02
**Authors:** Myro Productions

---

## Context

Bob Phase 1 established the core end-to-end voice pipeline: STT (FasterWhisper on Linux Desktop) → Rust desktop client → Anthropic Claude LLM → ElevenLabs TTS. Phase 1 completion work addressed three gaps that remained after the initial pipeline stood up:

1. **No live configuration** — changing temperature, max tokens, model, or system prompt required restarting the orchestrator process.
2. **No persistent process management** — Bob Control (the dashboard UI for the pipeline) had to be launched manually each session.
3. **No diagnostic tooling** — verifying that Meta glasses media key taps were being received required inference from pipeline behavior rather than direct observation.

## Decision

Three independent additions were shipped as a single Phase 1 completion batch:

### 1. Live Runtime Configuration Panel

A settings panel was added to the Bob Control dashboard (`src/bob-control/`) exposing temperature, max tokens, model selection, system prompt, and a clear-memory action. Changes take effect without restarting the orchestrator.

Backend surface added to the orchestrator (`src/orchestrator/`):
- `Session.set_params()` — applies temperature, max tokens, and model to a live session
- `Session.clear_history()` — flushes conversation history
- `POST /settings` — accepts a JSON body with any subset of `{temperature, max_tokens, model, system_prompt}`
- `POST /clear-memory` — resets conversation history

The process-manager proxy layer (`src/process-manager/`) gained:
- `GET /api/settings` — proxies to orchestrator
- `POST /api/settings` — proxies to orchestrator
- `POST /api/clear-memory` — proxies to orchestrator

Error status codes from upstream services are now propagated correctly through the proxy (previously all proxy errors surfaced as 502 regardless of upstream status).

### 2. Bob System Prompt Cleanup

The orchestrator was changed to load a clean prose system prompt (`system_prompt.md`) instead of the full steering-wheel markdown previously used. The new prompt reflects Bob's character: logical, direct, no filler phrases, no sycophancy. Barge-in suppression was also fixed — Bob no longer attempts to interrupt itself while in standby mode.

### 3. launchd Service for Bob Control

A `launchd` agent (`infra/mac/com.myroproductions.bob-control.plist`) starts the Bob Control process at login and keeps it alive via `KeepAlive`. `webbrowser.open` was removed from the startup path — `KeepAlive` was causing it to spawn a new browser window on every restart.

### 4. Hotkey Diagnostic Script

`src/hotkey-daemon/detect_key.py` — a diagnostic utility that listens for `NSSystemDefined` media key events and prints the raw key code and state to stdout. Used to verify that Meta glasses tap events are being received by the macOS event system before the daemon processes them.

## Options Considered

**Option A: Ship settings panel as a separate PR per component**
- More granular history, easier bisect
- Overkill for an internal prototype at this stage of development

**Option B: Bundle Phase 1 completion as one batch (chosen)**
- All three additions close the same gap: making Bob usable day-to-day without manual intervention
- Single ADR captures the cohesive intent

## Consequences

- Bob Control now starts automatically on login and requires no manual launch
- LLM parameters and system prompt can be tuned live from the dashboard without a restart
- `src/hotkey-daemon/detect_key.py` is tracked as a dev utility; it is not part of the runtime pipeline
- Phase 1 is considered complete; Phase 2 (Twilio ConversationRelay telephony) begins on a new development branch

## References

- ADR-006: Bob voice assistant architecture
- ADR-007: STT systemd deployment on Linux Desktop
- ADR-008: Persistent SSH tunnel for Mac-to-Linux STT connectivity
- `infra/mac/com.myroproductions.bob-control.plist`
- `src/orchestrator/session.py`
- `src/process-manager/`
- `src/bob-control/`
