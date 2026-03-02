# Bob Settings Panel & System Prompt Fix — Design

**Date:** 2026-03-01
**Status:** Approved

---

## Goal

Fix Bob's system prompt (currently the entire steering markdown doc), add a live settings panel to the right side of Bob Control (localhost:7766), and expose temperature / max tokens / model as runtime-adjustable controls requiring no restart.

## Architecture

### System Prompt
- Extract clean prose prompt into `docs/steering/bob-system-prompt.txt`
- Personality direction: warm, calm, present, logical positivity (not performative), concise, honest
- `src/orchestrator/main.py` loads this file instead of the full steering markdown

### Bob Control Layout Change
- Current grid: `grid-template-columns: 1fr 1fr`
- New grid: `grid-template-columns: 1fr 1fr 280px`
- New right column: settings card spanning full height alongside existing service cards
- Status bar still spans `1 / -1`
- Media Key Tap card spans columns 1–2 only (not 3)

### Settings Panel Controls
| Control | Type | Range | Default |
|---|---|---|---|
| Temperature | Slider + value readout | 0.0 – 1.0, step 0.05 | 0.6 |
| Max Response Tokens | Slider + value readout | 128 – 2048, step 64 | 512 |
| Model | Dropdown | Haiku 4.5 / Sonnet 4.6 / Opus 4.6 | Haiku 4.5 |
| Memory | Clear button | — | resets history |

Single "Apply" button saves temperature + max_tokens + model in one POST. Clear Memory is a separate button with immediate effect.

### New API Endpoints

**Orchestrator (port 8766):**
- `POST /settings` — body `{temperature?: float, max_tokens?: int, model?: str}` — updates live session, returns current values
- `POST /clear-memory` — resets `session._history` to `[]`, returns `{cleared: true}`

**Process-Manager (port 7766):**
- `POST /api/settings` — proxies to `http://127.0.0.1:8766/settings`
- `POST /api/clear-memory` — proxies to `http://127.0.0.1:8766/clear-memory`

### Session Changes (`session.py`)
- Add `set_params(temperature, max_tokens, model)` method — updates `_temperature`, `_max_tokens`, `_model` in place
- Add `clear_history()` method — resets `_history = []`
- `max_tokens` becomes instance variable (currently hardcoded 1024 in `_call_claude`)
- Default `max_tokens` drops from 1024 → 512

## Files Changed
- `docs/steering/bob-system-prompt.txt` — NEW: clean prose system prompt
- `src/orchestrator/session.py` — add `set_params()`, `clear_history()`, `_max_tokens` field
- `src/orchestrator/main.py` — load `bob-system-prompt.txt`, add `POST /settings`, `POST /clear-memory`
- `src/process-manager/app.py` — add `/api/settings`, `/api/clear-memory` proxy endpoints + settings panel HTML/CSS/JS

## Out of Scope
- Live system prompt editing in UI
- Cross-session memory persistence
- VAD sensitivity control (restart-required)
