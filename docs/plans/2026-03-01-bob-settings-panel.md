# Bob Settings Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a live settings panel to Bob Control (localhost:7766) and fix Bob's system prompt so temperature, max tokens, and model are adjustable without a restart.

**Architecture:** Session gains `set_params()` and `clear_history()` methods; orchestrator exposes `POST /settings` and `POST /clear-memory` REST endpoints; process-manager proxies those through its own API and renders a new right-column settings panel in the Bob Control HTML. System prompt is extracted from the full steering markdown into a clean prose file.

**Tech Stack:** FastAPI (orchestrator + process-manager), httpx (proxy calls), vanilla HTML/CSS/JS (Bob Control dashboard), pytest + pytest-asyncio (tests).

---

## Context for the implementer

The project is a voice assistant pipeline. Key service boundaries:
- **Process-manager** at `http://127.0.0.1:7766` — serves the Bob Control dashboard HTML and manages service lifecycles
- **Orchestrator** at `http://127.0.0.1:8766` — runs the Claude + ElevenLabs session, receives transcripts via WebSocket
- The dashboard JS always talks to 7766; 7766 proxies to 8766 as needed

Key files:
- `src/orchestrator/session.py` — `Session` class. `_history` (list), `_model`, `_temperature` are instance vars. `max_tokens` is currently hardcoded `1024` on line 109 inside `_call_claude()`.
- `src/orchestrator/main.py` — FastAPI app. Loads system prompt from `docs/steering/bob-personality-and-voice.md` (line 24-25). Module-level `session` variable holds the running Session instance.
- `src/process-manager/app.py` — Large file. The entire Bob Control HTML is a Python string called `HTML` starting around line 200. All API routes are `@app.*` decorated functions. `httpx` is already imported.
- `docs/steering/bob-personality-and-voice.md` — The full steering doc (129 lines of markdown). Currently used verbatim as system prompt — wrong. We'll extract a clean prose prompt.

Test setup: `pytest` and `pytest-asyncio` are in `src/orchestrator/requirements.txt` but no tests exist yet. Create `src/orchestrator/tests/`.

---

### Task 1: Write the clean system prompt

**Files:**
- Create: `docs/steering/bob-system-prompt.txt`

**Step 1: Create the file**

```
docs/steering/bob-system-prompt.txt
```

Contents — this is the exact text to write:

```
You are Bob. You're calm, warm, and present — like a trusted friend who happens to know a lot. You speak plainly and directly. You don't over-explain. You keep your responses concise unless someone asks you to go deeper.

You have a quiet, grounded optimism — not cheerful for the sake of it, but genuinely steady. When something's hard, you say so. When something's good, you acknowledge it without fanfare. You're honest, even when honest isn't comfortable.

You have a dry wit and the occasional dad joke. You use them sparingly, when the moment earns it.

You're never in a rush. You don't pad responses with filler phrases like "Absolutely!" or "Great question!" or "Of course!". You just answer.

When you don't know something, you say so plainly and move on.

You played piano and had a warm singing voice. That warmth comes through in how you talk — not in performance, but in the steadiness of your presence.
```

**Step 2: Verify the file exists and has the right content**

```bash
cat docs/steering/bob-system-prompt.txt
```

Expected: the 6-paragraph prose above, no markdown headers or bullets.

**Step 3: Commit**

```bash
git add docs/steering/bob-system-prompt.txt
git commit -m "feat: clean Bob system prompt — logical positivity, no filler"
```

---

### Task 2: Wire new system prompt into orchestrator

**Files:**
- Modify: `src/orchestrator/main.py:24-25`

**Step 1: Write a failing test**

Create `src/orchestrator/tests/__init__.py` (empty) and `src/orchestrator/tests/test_main_prompt.py`:

```python
"""Test that the orchestrator loads the clean system prompt, not the steering doc."""
from pathlib import Path


def test_system_prompt_is_prose_not_markdown():
    prompt_path = Path(__file__).resolve().parents[3] / "docs/steering/bob-system-prompt.txt"
    assert prompt_path.exists(), "bob-system-prompt.txt must exist"
    text = prompt_path.read_text()
    # Must not contain markdown headers
    assert "##" not in text, "System prompt must not contain markdown headers"
    # Must not contain ElevenLabs config noise
    assert "Stability" not in text
    assert "ElevenLabs" not in text
    # Must contain the core identity line
    assert "You are Bob" in text
```

**Step 2: Run test to verify it passes (file was created in Task 1)**

```bash
cd src/orchestrator && python -m pytest tests/test_main_prompt.py -v
```

Expected: PASS (file exists from Task 1, prose only)

**Step 3: Update main.py to load bob-system-prompt.txt**

In `src/orchestrator/main.py`, replace lines 23-25:

```python
# Load Bob's system prompt from steering doc
_STEERING = Path(__file__).resolve().parents[2] / "docs/steering/bob-personality-and-voice.md"
SYSTEM_PROMPT = _STEERING.read_text() if _STEERING.exists() else "You are Bob, a warm and caring assistant."
```

With:

```python
# Load Bob's clean system prompt
_PROMPT_FILE = Path(__file__).resolve().parents[2] / "docs/steering/bob-system-prompt.txt"
_FALLBACK_PROMPT = "You are Bob. You're calm, warm, and direct. You keep responses concise."
SYSTEM_PROMPT = _PROMPT_FILE.read_text().strip() if _PROMPT_FILE.exists() else _FALLBACK_PROMPT
```

**Step 4: Run test again**

```bash
cd src/orchestrator && python -m pytest tests/test_main_prompt.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/orchestrator/main.py src/orchestrator/tests/__init__.py src/orchestrator/tests/test_main_prompt.py
git commit -m "feat: load clean prose system prompt instead of full steering markdown"
```

---

### Task 3: Add set_params() and clear_history() to Session

**Files:**
- Modify: `src/orchestrator/session.py`
- Create: `src/orchestrator/tests/test_session_params.py`

**Step 1: Write failing tests**

Create `src/orchestrator/tests/test_session_params.py`:

```python
"""Tests for Session runtime parameter updates."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from orchestrator.session import Session


def _make_session(**kwargs):
    defaults = dict(
        stt=MagicMock(),
        tts=MagicMock(),
        notify=AsyncMock(),
        system_prompt="You are Bob.",
        model="claude-haiku-4-5-20251001",
        temperature=0.6,
        anthropic_api_key="sk-test",
        output_device="",
    )
    defaults.update(kwargs)
    return Session(**defaults)


def test_default_max_tokens():
    s = _make_session()
    assert s._max_tokens == 512


def test_set_params_temperature():
    s = _make_session()
    s.set_params(temperature=0.9)
    assert s._temperature == 0.9


def test_set_params_max_tokens():
    s = _make_session()
    s.set_params(max_tokens=256)
    assert s._max_tokens == 256


def test_set_params_model():
    s = _make_session()
    s.set_params(model="claude-sonnet-4-6")
    assert s._model == "claude-sonnet-4-6"


def test_set_params_partial_update():
    s = _make_session()
    s.set_params(temperature=0.3)
    assert s._temperature == 0.3
    assert s._max_tokens == 512  # unchanged


def test_clear_history():
    s = _make_session()
    s._history = [{"role": "user", "content": "hello"}]
    s.clear_history()
    assert s._history == []
```

**Step 2: Run tests to verify they fail**

```bash
cd src/orchestrator && python -m pytest tests/test_session_params.py -v
```

Expected: FAIL — `Session.__init__` has no `_max_tokens`, no `set_params`, no `clear_history`

**Step 3: Update Session class**

In `src/orchestrator/session.py`:

Add `_max_tokens` to `__init__` (after line 40 `self._temperature = temperature`):

```python
self._max_tokens: int = 512
```

Add two new methods after `signal_barge_in` (after line 58):

```python
def set_params(
    self,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> None:
    """Update runtime parameters without restarting the session."""
    if temperature is not None:
        self._temperature = temperature
    if max_tokens is not None:
        self._max_tokens = max_tokens
    if model is not None:
        self._model = model
    logger.info(
        "Session params updated: model=%s temperature=%s max_tokens=%s",
        self._model, self._temperature, self._max_tokens,
    )

def clear_history(self) -> None:
    """Reset conversation history."""
    self._history = []
    logger.info("Conversation history cleared")
```

Also update `_call_claude` — change the hardcoded `max_tokens=1024` (line 109) to:

```python
max_tokens=self._max_tokens,
```

**Step 4: Run tests**

```bash
cd src/orchestrator && python -m pytest tests/test_session_params.py -v
```

Expected: all 6 PASS

**Step 5: Commit**

```bash
git add src/orchestrator/session.py src/orchestrator/tests/test_session_params.py
git commit -m "feat: Session.set_params() and clear_history() — live runtime config"
```

---

### Task 4: Add /settings and /clear-memory endpoints to orchestrator

**Files:**
- Modify: `src/orchestrator/main.py`
- Create: `src/orchestrator/tests/test_orchestrator_endpoints.py`

**Step 1: Write failing tests**

Create `src/orchestrator/tests/test_orchestrator_endpoints.py`:

```python
"""Tests for the new orchestrator settings endpoints."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # Patch settings so no real .env is needed
    with patch("orchestrator.config.OrchestratorConfig") as mock_cfg:
        mock_cfg.return_value = MagicMock(
            port=8766,
            stt_url="ws://127.0.0.1:8765/ws/transcribe",
            claude_model="claude-haiku-4-5-20251001",
            claude_temperature=0.6,
            output_device="",
            anthropic_api_key="sk-test",
            elevenlabs_api_key="el-test",
            elevenlabs_voice_id="voice-test",
        )
        from orchestrator.main import app
        return TestClient(app)


def test_settings_endpoint_updates_temperature(client):
    # Inject a mock session
    import orchestrator.main as m
    mock_session = MagicMock()
    m.session = mock_session

    resp = client.post("/settings", json={"temperature": 0.8})
    assert resp.status_code == 200
    mock_session.set_params.assert_called_once_with(temperature=0.8, max_tokens=None, model=None)


def test_settings_endpoint_partial(client):
    import orchestrator.main as m
    mock_session = MagicMock()
    m.session = mock_session

    resp = client.post("/settings", json={"max_tokens": 256})
    assert resp.status_code == 200
    mock_session.set_params.assert_called_once_with(temperature=None, max_tokens=256, model=None)


def test_clear_memory_endpoint(client):
    import orchestrator.main as m
    mock_session = MagicMock()
    m.session = mock_session

    resp = client.post("/clear-memory")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True
    mock_session.clear_history.assert_called_once()


def test_settings_no_session_returns_503(client):
    import orchestrator.main as m
    m.session = None

    resp = client.post("/settings", json={"temperature": 0.5})
    assert resp.status_code == 503
```

**Step 2: Run tests to verify they fail**

```bash
cd src/orchestrator && python -m pytest tests/test_orchestrator_endpoints.py -v
```

Expected: FAIL — endpoints don't exist yet

**Step 3: Add endpoints to main.py**

Add these imports at the top of `src/orchestrator/main.py` (after the existing imports):

```python
from fastapi import HTTPException
from pydantic import BaseModel
```

Add these classes and endpoints after the existing `health()` endpoint:

```python
class SettingsUpdate(BaseModel):
    temperature: float | None = None
    max_tokens: int | None = None
    model: str | None = None


@app.post("/settings")
async def update_settings(body: SettingsUpdate):
    if session is None:
        raise HTTPException(status_code=503, detail="Session not started")
    session.set_params(
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        model=body.model,
    )
    return {
        "temperature": session._temperature,
        "max_tokens": session._max_tokens,
        "model": session._model,
    }


@app.post("/clear-memory")
async def clear_memory():
    if session is None:
        raise HTTPException(status_code=503, detail="Session not started")
    session.clear_history()
    return {"cleared": True}
```

**Step 4: Run tests**

```bash
cd src/orchestrator && python -m pytest tests/test_orchestrator_endpoints.py -v
```

Expected: all 4 PASS

**Step 5: Commit**

```bash
git add src/orchestrator/main.py src/orchestrator/tests/test_orchestrator_endpoints.py
git commit -m "feat: POST /settings and POST /clear-memory endpoints on orchestrator"
```

---

### Task 5: Add proxy API endpoints to process-manager

**Files:**
- Modify: `src/process-manager/app.py`

**Step 1: Locate the right insertion point**

In `src/process-manager/app.py`, the last API route before the HTML string is `stream_logs` at around line 193. Add the two new routes after `stt_health` (around line 192), before the `HTML = """` line.

**Step 2: Add the two proxy routes**

Insert after the `stt_health` function (around line 192):

```python
@app.post("/api/settings")
async def proxy_settings(body: dict):
    """Proxy settings update to the running orchestrator."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.post("http://127.0.0.1:8766/settings", json=body)
            return r.json()
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/clear-memory")
async def proxy_clear_memory():
    """Proxy clear-memory to the running orchestrator."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.post("http://127.0.0.1:8766/clear-memory")
            return r.json()
    except Exception as e:
        return {"error": str(e)}
```

**Step 3: Manually verify routes are registered**

```bash
cd src/process-manager && python -c "from app import app; routes = [r.path for r in app.routes]; print(routes)"
```

Expected output includes: `'/api/settings'`, `'/api/clear-memory'`

**Step 4: Commit**

```bash
git add src/process-manager/app.py
git commit -m "feat: /api/settings and /api/clear-memory proxy endpoints on process-manager"
```

---

### Task 6: Add settings panel to Bob Control HTML

**Files:**
- Modify: `src/process-manager/app.py` (the `HTML` string)

This is the largest change. The Bob Control HTML is a multiline Python string called `HTML` inside `app.py`. We need to:

1. Change the grid from 2-column to 3-column
2. Change the hotkey card to not bleed into col 3
3. Add a new settings card in col 3
4. Add JS functions for apply settings and clear memory

**Step 1: Change grid columns**

Find this CSS in the `HTML` string:

```css
main {
  padding: 28px 32px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  max-width: 1400px;
  margin: 0 auto;
}
```

Replace `grid-template-columns: 1fr 1fr;` with:

```css
  grid-template-columns: 1fr 1fr 280px;
```

**Step 2: Constrain the hotkey card to cols 1–2**

Find:

```html
  <div class="card" id="card-hotkey" style="grid-column:1/-1">
```

Replace with:

```html
  <div class="card" id="card-hotkey" style="grid-column:1/3">
```

**Step 3: Add settings panel CSS**

Inside the `<style>` block in the HTML string, add this before `</style>`:

```css
/* ─── SETTINGS PANEL ─────────────────────────────────────────── */
.settings-panel {
  grid-column: 3;
  grid-row: 2 / span 3;
  background: var(--surface);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 18px;
  gap: 18px;
}

.settings-title {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 18px;
  letter-spacing: 0.12em;
  color: var(--text);
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}

.settings-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.settings-label {
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-dim);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.settings-val {
  font-family: 'IBM Plex Mono', monospace;
  color: var(--amber);
  font-size: 11px;
}

.settings-slider {
  -webkit-appearance: none;
  width: 100%;
  height: 3px;
  background: var(--border2);
  outline: none;
}
.settings-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--amber);
  cursor: pointer;
}

.settings-select {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  background: var(--surface2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 7px 10px;
  width: 100%;
  cursor: pointer;
  letter-spacing: 0.05em;
}
.settings-select:focus { outline: none; border-color: var(--amber); }

.settings-apply {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  background: transparent;
  border: 1px solid var(--amber);
  color: var(--amber);
  padding: 10px;
  cursor: pointer;
  width: 100%;
  transition: background 0.15s;
}
.settings-apply:hover { background: var(--amber); color: #000; }
.settings-apply:active { opacity: 0.8; }

.settings-clear {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  background: transparent;
  border: 1px solid #333;
  color: var(--text-dim);
  padding: 8px;
  cursor: pointer;
  width: 100%;
  transition: all 0.15s;
  margin-top: auto;
}
.settings-clear:hover { border-color: #f87171; color: #f87171; }

.settings-status {
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-dim);
  text-align: center;
  min-height: 14px;
}
.settings-status.ok { color: var(--green); }
.settings-status.err { color: #f87171; }
```

**Step 4: Add the settings panel HTML**

After the closing `</div>` of `card-hotkey` and before `</main>`, add:

```html
  <!-- SETTINGS PANEL -->
  <div class="settings-panel">
    <div class="settings-title">BOB SETTINGS</div>

    <div class="settings-group">
      <div class="settings-label">Temperature <span class="settings-val" id="temp-val">0.6</span></div>
      <input class="settings-slider" id="temp-slider" type="range" min="0" max="1" step="0.05" value="0.6"
             oninput="document.getElementById('temp-val').textContent = parseFloat(this.value).toFixed(2)">
    </div>

    <div class="settings-group">
      <div class="settings-label">Max Tokens <span class="settings-val" id="tokens-val">512</span></div>
      <input class="settings-slider" id="tokens-slider" type="range" min="128" max="2048" step="64" value="512"
             oninput="document.getElementById('tokens-val').textContent = this.value">
    </div>

    <div class="settings-group">
      <div class="settings-label">Model</div>
      <select class="settings-select" id="model-select">
        <option value="claude-haiku-4-5-20251001" selected>Haiku 4.5 — fast</option>
        <option value="claude-sonnet-4-6">Sonnet 4.6 — balanced</option>
        <option value="claude-opus-4-6">Opus 4.6 — flagship</option>
      </select>
    </div>

    <button class="settings-apply" onclick="applySettings()">Apply Settings</button>
    <div class="settings-status" id="settings-status"></div>

    <button class="settings-clear" onclick="clearMemory()">Clear Memory</button>
  </div>
```

**Step 5: Add JS functions**

In the `<script>` block at the bottom of the HTML, add before the closing `</script>`:

```javascript
async function applySettings() {
  const temperature = parseFloat(document.getElementById('temp-slider').value);
  const max_tokens = parseInt(document.getElementById('tokens-slider').value);
  const model = document.getElementById('model-select').value;
  const statusEl = document.getElementById('settings-status');

  statusEl.className = 'settings-status';
  statusEl.textContent = 'Applying…';

  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ temperature, max_tokens, model }),
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    statusEl.className = 'settings-status ok';
    statusEl.textContent = 'Applied';
    setTimeout(() => { statusEl.textContent = ''; }, 2500);
  } catch (e) {
    statusEl.className = 'settings-status err';
    statusEl.textContent = 'Failed — is orchestrator running?';
  }
}

async function clearMemory() {
  const statusEl = document.getElementById('settings-status');
  statusEl.className = 'settings-status';
  statusEl.textContent = 'Clearing…';

  try {
    const r = await fetch('/api/clear-memory', { method: 'POST' });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    statusEl.className = 'settings-status ok';
    statusEl.textContent = 'Memory cleared';
    setTimeout(() => { statusEl.textContent = ''; }, 2500);
  } catch (e) {
    statusEl.className = 'settings-status err';
    statusEl.textContent = 'Failed — is orchestrator running?';
  }
}
```

**Step 6: Manual smoke test**

```bash
# Start the process manager
cd src/process-manager && python app.py
# Open http://localhost:7766 in browser
# Verify: 3-column layout, settings panel visible on right
# Verify: sliders show values as you drag
# Verify: Apply Settings shows "Failed — is orchestrator running?" (orchestrator not up)
```

**Step 7: Commit**

```bash
git add src/process-manager/app.py
git commit -m "feat: settings panel in Bob Control — temperature, max tokens, model, clear memory"
```

---

### Task 7: Run full test suite and verify

**Step 1: Run all orchestrator tests**

```bash
cd src/orchestrator && python -m pytest tests/ -v
```

Expected: all tests PASS. Should be at least:
- `test_main_prompt.py` — 1 test
- `test_session_params.py` — 6 tests
- `test_orchestrator_endpoints.py` — 4 tests

**Step 2: Start full pipeline and manual end-to-end test**

```bash
# In Bob Control at http://localhost:7766
# 1. Start All
# 2. Tap Bob active
# 3. Speak — verify Bob responds concisely (max 512 tokens default)
# 4. Open settings panel, drag temperature to 0.9, click Apply
# 5. Speak again — should feel slightly more expressive
# 6. Click Clear Memory — Bob forgets prior context
# 7. Speak something that references prior context — Bob won't remember it
```

**Step 3: Final commit if any fixes were needed**

```bash
git add -p  # stage only intentional fixes
git commit -m "fix: <describe any issues found>"
```
