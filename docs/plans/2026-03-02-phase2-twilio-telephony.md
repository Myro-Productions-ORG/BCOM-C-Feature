# Phase 2 — Twilio ConversationRelay + ElevenLabs Telephony Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add inbound and outbound phone call support to Bob using Twilio ConversationRelay with ElevenLabs as the native TTS provider, keeping Anthropic Claude as the LLM.

**Architecture:** A new `telephony-adapter` FastAPI service (port 8767) sits between Twilio ConversationRelay and the Anthropic API. Each phone call gets its own `CallSession` with isolated conversation history. Twilio handles STT and calls ElevenLabs directly for TTS — the adapter only needs to receive transcripts and return text. The adapter is exposed publicly via the existing Caddy + Cloudflare tunnel at `bcom.myroproductions.com`.

**Tech Stack:** Python 3.11+, FastAPI, `twilio` SDK (REST API + TwiML), `anthropic` SDK, uvicorn, pytest, pytest-asyncio.

---

## Background: Key Files

- `src/orchestrator/session.py` — existing Claude session (for reference/pattern, NOT imported by telephony-adapter)
- `src/orchestrator/config.py` — pattern to follow for pydantic-settings config
- `src/process-manager/app.py` — add telephony-adapter as a managed service here
- `.env` — add Twilio credentials here
- Caddy config lives in a Docker container on nicolasmac at 10.0.0.223

## Background: ConversationRelay WebSocket Protocol

Twilio connects to our WebSocket after the call is answered. Message flow:

**Twilio → us:**
```json
{"type": "setup", "callSid": "CA...", "from": "+1...", "to": "+1..."}
{"type": "prompt", "voicePrompt": "Hello Bob", "last": true}
{"type": "interrupt", "utteranceUntilInterrupt": "Hello", "durationUntilInterruptMs": 500}
{"type": "dtmf", "digit": "1"}
```

**Us → Twilio:**
```json
{"type": "text", "token": "Hey! ", "last": false}
{"type": "text", "token": "How can I help?", "last": true}
{"type": "end"}
```

Stream Claude response tokens as `{"type":"text","token":"...","last":false}`, then send final token with `"last":true`. Twilio buffers them and uses ElevenLabs to synthesize.

## Background: ElevenLabs Voice Format in TwiML

```xml
<ConversationRelay
  url="wss://bcom.myroproductions.com/telephony/ws/conversation"
  ttsProvider="ElevenLabs"
  voice="{VOICE_ID}"
  welcomeGreeting="Hey, this is Bob. What can I do for you?"
/>
```

The `voice` attribute takes the raw ElevenLabs voice ID (e.g., `27ugurx8r230xq5a0vKV`). Model and voice customization parameters (speed, stability, similarity) can be appended in the format `{voiceId}-{model}-{speed}_{stability}_{similarity}` — verify exact format against Twilio docs at https://www.twilio.com/en-us/blog/integrate-elevenlabs-voices-with-twilios-conversationrelay before using parameterized form.

---

## Task 1: Scaffold telephony-adapter — config, requirements, health endpoint

**Files:**
- Create: `src/telephony-adapter/__init__.py`
- Create: `src/telephony-adapter/requirements.txt`
- Create: `src/telephony-adapter/config.py`
- Create: `src/telephony-adapter/main.py`
- Create: `src/telephony-adapter/tests/__init__.py`
- Create: `src/telephony-adapter/tests/test_health.py`

**Step 1: Create requirements.txt**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
twilio>=9.0.0
anthropic>=0.40.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

**Step 2: Set up venv and install**

```bash
cd src/telephony-adapter
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Step 3: Create `src/telephony-adapter/__init__.py`** (empty file)

**Step 4: Create `src/telephony-adapter/config.py`**

```python
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class TelephonyConfig(BaseSettings):
    port: int = 8767
    public_base_url: str = "https://bcom.myroproductions.com/telephony"

    # Twilio credentials
    twilio_account_sid: str = Field(
        validation_alias=AliasChoices("TWILIO_ACCOUNT_SID", "TELEPHONY_TWILIO_ACCOUNT_SID")
    )
    twilio_api_key_sid: str = Field(
        validation_alias=AliasChoices("TWILIO_SID", "TELEPHONY_TWILIO_API_KEY_SID")
    )
    twilio_api_key_secret: str = Field(
        validation_alias=AliasChoices("TWILIO_SECRET", "TELEPHONY_TWILIO_API_KEY_SECRET")
    )
    twilio_phone_number: str = Field(
        validation_alias=AliasChoices("TWILIO_PHONE_NUMBER", "TELEPHONY_TWILIO_PHONE_NUMBER")
    )

    # Anthropic
    anthropic_api_key: str = Field(
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "TELEPHONY_ANTHROPIC_API_KEY")
    )
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_temperature: float = 0.6
    claude_max_tokens: int = 512

    # ElevenLabs voice (used in TwiML)
    elevenlabs_voice_id: str = Field(
        validation_alias=AliasChoices("ELEVENLABS_VOICE_ID", "TELEPHONY_ELEVENLABS_VOICE_ID")
    )

    model_config = {
        "env_prefix": "TELEPHONY_",
        "env_file": str(_ENV_FILE),
        "extra": "ignore",
    }


settings = TelephonyConfig()
```

**Step 5: Write the failing test**

```python
# src/telephony-adapter/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
import os

os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_SID", "SKtest")
os.environ.setdefault("TWILIO_SECRET", "testsecret")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "testvoice")


def test_import():
    from telephony_adapter.main import app
    assert app is not None


@pytest.mark.asyncio
async def test_health():
    from telephony_adapter.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

**Step 6: Run test to verify it fails**

```bash
cd src/telephony-adapter
source venv/bin/activate
PYTHONPATH=.. pytest tests/test_health.py -v
```
Expected: ImportError or ModuleNotFoundError (main.py doesn't exist yet)

**Step 7: Create `src/telephony-adapter/main.py`**

```python
"""Telephony adapter — Twilio ConversationRelay + ElevenLabs TTS + Anthropic Claude."""

import logging
from fastapi import FastAPI
import uvicorn

from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bob Telephony Adapter")


@app.get("/health")
async def health():
    return {"status": "ok", "port": settings.port}


if __name__ == "__main__":
    uvicorn.run(
        "telephony_adapter.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
    )
```

Note: the module name is `telephony_adapter` (underscore) because Python package names can't have hyphens. The directory is `src/telephony-adapter/` but we import it as `telephony_adapter`. Add a symlink or run with PYTHONPATH set to `src/`.

Actually: rename the directory to `telephony_adapter` to avoid confusion:
```bash
mv src/telephony-adapter src/telephony_adapter
```

Update all references in this plan accordingly (`src/telephony_adapter/`).

**Step 8: Run test to verify it passes**

```bash
cd src/telephony_adapter
source venv/bin/activate
PYTHONPATH=.. pytest tests/test_health.py -v
```
Expected: PASS

**Step 9: Commit**

```bash
git add src/telephony_adapter/
git commit -m "feat: scaffold telephony-adapter service — health endpoint"
```

---

## Task 2: TwiML inbound webhook

Bob needs to respond to Twilio with XML that activates ConversationRelay using ElevenLabs as the TTS provider.

**Files:**
- Create: `src/telephony_adapter/twiml.py`
- Create: `src/telephony_adapter/tests/test_twiml.py`
- Modify: `src/telephony_adapter/main.py`

**Step 1: Write the failing test**

```python
# src/telephony_adapter/tests/test_twiml.py
import os
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_SID", "SKtest")
os.environ.setdefault("TWILIO_SECRET", "testsecret")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "testvoiceid")

from telephony_adapter.twiml import build_conversation_relay_twiml


def test_twiml_contains_conversationrelay():
    xml = build_conversation_relay_twiml(
        ws_url="wss://example.com/telephony/ws/conversation",
        voice_id="testvoiceid",
        greeting="Hello",
    )
    assert "<ConversationRelay" in xml
    assert 'ttsProvider="ElevenLabs"' in xml
    assert "testvoiceid" in xml
    assert "wss://example.com/telephony/ws/conversation" in xml
    assert "Hello" in xml


def test_twiml_is_valid_xml():
    import xml.etree.ElementTree as ET
    xml = build_conversation_relay_twiml(
        ws_url="wss://example.com/ws",
        voice_id="v123",
        greeting="Hi",
    )
    ET.fromstring(xml)  # raises if invalid XML
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=.. pytest tests/test_twiml.py -v
```
Expected: ImportError (twiml.py doesn't exist)

**Step 3: Create `src/telephony_adapter/twiml.py`**

```python
"""TwiML response builders for Twilio ConversationRelay."""


def build_conversation_relay_twiml(
    ws_url: str,
    voice_id: str,
    greeting: str = "Hey, this is Bob. What can I do for you?",
) -> str:
    """Return TwiML XML string that activates ConversationRelay with ElevenLabs TTS."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay
      url="{ws_url}"
      ttsProvider="ElevenLabs"
      voice="{voice_id}"
      welcomeGreeting="{greeting}"
    />
  </Connect>
</Response>"""
```

**Step 4: Add inbound webhook route to `main.py`**

Add these imports at the top:
```python
from fastapi import Request
from fastapi.responses import Response
from .twiml import build_conversation_relay_twiml
```

Add this route:
```python
@app.post("/twiml/inbound")
async def twiml_inbound(request: Request):
    """Twilio webhook for inbound calls — returns ConversationRelay TwiML."""
    ws_url = f"{settings.public_base_url}/ws/conversation"
    xml = build_conversation_relay_twiml(
        ws_url=ws_url,
        voice_id=settings.elevenlabs_voice_id,
    )
    logger.info("Inbound call — returning ConversationRelay TwiML, ws=%s", ws_url)
    return Response(content=xml, media_type="application/xml")
```

**Step 5: Run tests**

```bash
PYTHONPATH=.. pytest tests/ -v
```
Expected: All PASS

**Step 6: Commit**

```bash
git add src/telephony_adapter/
git commit -m "feat: TwiML inbound webhook — ConversationRelay with ElevenLabs TTS"
```

---

## Task 3: CallSession — per-call Claude conversation

Each phone call gets its own conversation history and Claude API client.

**Files:**
- Create: `src/telephony_adapter/call_session.py`
- Create: `src/telephony_adapter/tests/test_call_session.py`

**Step 1: Write the failing test**

```python
# src/telephony_adapter/tests/test_call_session.py
import os
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_SID", "SKtest")
os.environ.setdefault("TWILIO_SECRET", "testsecret")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "testvoiceid")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telephony_adapter.call_session import CallSession


def test_call_session_init():
    session = CallSession(call_sid="CA123", model="claude-haiku-4-5-20251001")
    assert session.call_sid == "CA123"
    assert session.history == []


@pytest.mark.asyncio
async def test_respond_appends_history():
    """respond() adds user message and assistant reply to history."""
    session = CallSession(call_sid="CA123", model="claude-haiku-4-5-20251001")

    async def fake_stream(text):
        yield "Hello "
        yield "there!"

    with patch.object(session, "_stream_claude", side_effect=fake_stream):
        chunks = []
        async for chunk, is_last in session.respond("Hi Bob"):
            chunks.append((chunk, is_last))

    assert any(is_last for _, is_last in chunks)
    full_text = "".join(c for c, _ in chunks)
    assert full_text == "Hello there!"
    assert session.history[-1] == {"role": "assistant", "content": "Hello there!"}
    assert session.history[-2] == {"role": "user", "content": "Hi Bob"}
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=.. pytest tests/test_call_session.py -v
```
Expected: ImportError

**Step 3: Create `src/telephony_adapter/call_session.py`**

```python
"""Per-call Claude session with conversation history."""

import logging
from typing import AsyncIterator

import anthropic

from .config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Bob, a calm and direct voice assistant. "
    "Keep responses concise — you are speaking on a phone call. "
    "No lists or markdown. Speak naturally."
)


class CallSession:
    def __init__(
        self,
        call_sid: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.call_sid = call_sid
        self.history: list[dict] = []
        self._model = model or settings.claude_model
        self._temperature = temperature or settings.claude_temperature
        self._max_tokens = max_tokens or settings.claude_max_tokens
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def respond(self, user_text: str) -> AsyncIterator[tuple[str, bool]]:
        """
        Yield (token, is_last) pairs for the Claude response to user_text.
        Appends both turns to history when complete.
        """
        self.history.append({"role": "user", "content": user_text})
        full_response = ""

        async for token in self._stream_claude(user_text):
            full_response += token
            yield token, False

        # Signal end with the last empty token marked last=True
        yield "", True
        self.history.append({"role": "assistant", "content": full_response})
        logger.info("[%s] Bob: %s", self.call_sid, full_response)

    async def _stream_claude(self, _: str) -> AsyncIterator[str]:
        """Stream tokens from Claude using current history (last message already appended)."""
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=SYSTEM_PROMPT,
            messages=self.history,
        ) as stream:
            async for event in stream:
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    yield event.delta.text
```

**Step 4: Run test to verify it passes**

```bash
PYTHONPATH=.. pytest tests/test_call_session.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/telephony_adapter/call_session.py src/telephony_adapter/tests/test_call_session.py
git commit -m "feat: CallSession — per-call Claude conversation with streaming"
```

---

## Task 4: ConversationRelay WebSocket handler

This is the core of the integration. Twilio connects here after ConversationRelay starts.

**Files:**
- Create: `src/telephony_adapter/tests/test_ws_handler.py`
- Modify: `src/telephony_adapter/main.py`

**Step 1: Write the failing test**

```python
# src/telephony_adapter/tests/test_ws_handler.py
import os
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_SID", "SKtest")
os.environ.setdefault("TWILIO_SECRET", "testsecret")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "testvoiceid")

import json
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from telephony_adapter.main import app


@pytest.mark.asyncio
async def test_ws_conversation_setup_message():
    """WebSocket accepts setup message without error."""
    from starlette.testclient import TestClient
    with TestClient(app) as client:
        with client.websocket_connect("/ws/conversation") as ws:
            ws.send_text(json.dumps({
                "type": "setup",
                "callSid": "CA123",
                "from": "+15550000001",
                "to": "+15550000000",
            }))
            # After setup, no response is sent — connection stays open


@pytest.mark.asyncio
async def test_ws_conversation_prompt_triggers_response():
    """WebSocket prompt message results in text response messages."""
    from starlette.testclient import TestClient

    async def fake_respond(user_text):
        yield "Hey there!", True

    with patch("telephony_adapter.main.CallSession") as MockSession:
        mock_session_instance = MagicMock()
        mock_session_instance.respond = AsyncMock(side_effect=fake_respond)
        MockSession.return_value = mock_session_instance

        with TestClient(app) as client:
            with client.websocket_connect("/ws/conversation") as ws:
                ws.send_text(json.dumps({"type": "setup", "callSid": "CA123"}))
                ws.send_text(json.dumps({
                    "type": "prompt",
                    "voicePrompt": "Hello Bob",
                    "last": True,
                }))
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "text"
                assert msg["last"] is True
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=.. pytest tests/test_ws_handler.py -v
```
Expected: FAIL — no `/ws/conversation` route

**Step 3: Add WebSocket handler to `main.py`**

Add imports at the top of main.py:
```python
import json
from fastapi import WebSocket, WebSocketDisconnect
from .call_session import CallSession
```

Add a module-level dict to track active sessions:
```python
_active_sessions: dict[str, CallSession] = {}
```

Add the WebSocket route:
```python
@app.websocket("/ws/conversation")
async def conversation_ws(ws: WebSocket):
    """ConversationRelay WebSocket — receives transcripts, streams Claude responses."""
    await ws.accept()
    session: CallSession | None = None

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "setup":
                call_sid = msg.get("callSid", "unknown")
                session = CallSession(call_sid=call_sid)
                _active_sessions[call_sid] = session
                logger.info("ConversationRelay session started: %s", call_sid)

            elif msg_type == "prompt" and session:
                user_text = msg.get("voicePrompt", "").strip()
                if not user_text:
                    continue
                logger.info("[%s] User: %s", session.call_sid, user_text)

                async for token, is_last in session.respond(user_text):
                    await ws.send_text(json.dumps({
                        "type": "text",
                        "token": token,
                        "last": is_last,
                    }))

            elif msg_type == "interrupt" and session:
                logger.info("[%s] Caller interrupted", session.call_sid)
                # Twilio stops playback; we just log and let the next prompt come in

            elif msg_type == "dtmf":
                logger.info("[%s] DTMF: %s", getattr(session, "call_sid", "?"), msg.get("digit"))

            elif msg_type == "error":
                logger.error("ConversationRelay error: %s", msg)

    except WebSocketDisconnect:
        if session:
            call_sid = session.call_sid
            _active_sessions.pop(call_sid, None)
            logger.info("ConversationRelay session ended: %s", call_sid)
```

**Step 4: Run all tests**

```bash
PYTHONPATH=.. pytest tests/ -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/telephony_adapter/
git commit -m "feat: ConversationRelay WebSocket handler — streams Claude tokens to Twilio"
```

---

## Task 5: Outbound call endpoint

**Files:**
- Create: `src/telephony_adapter/tests/test_outbound.py`
- Modify: `src/telephony_adapter/main.py`

**Step 1: Write the failing test**

```python
# src/telephony_adapter/tests/test_outbound.py
import os
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_SID", "SKtest")
os.environ.setdefault("TWILIO_SECRET", "testsecret")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "testvoiceid")

import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from telephony_adapter.main import app


@pytest.mark.asyncio
async def test_outbound_call_returns_call_sid():
    mock_call = MagicMock()
    mock_call.sid = "CA_outbound_123"

    with patch("telephony_adapter.main._twilio_client") as mock_client:
        mock_client.calls.create.return_value = mock_call
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/calls/outbound", json={"to": "+15550000001"})

    assert resp.status_code == 200
    assert resp.json()["call_sid"] == "CA_outbound_123"


@pytest.mark.asyncio
async def test_outbound_call_missing_to():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/calls/outbound", json={})
    assert resp.status_code == 422
```

**Step 2: Run test to verify it fails**

```bash
PYTHONPATH=.. pytest tests/test_outbound.py -v
```
Expected: FAIL — no `/calls/outbound` route

**Step 3: Add Twilio REST client and outbound endpoint to `main.py`**

Add imports:
```python
from pydantic import BaseModel
from twilio.rest import Client as TwilioClient
```

Add client instantiation after imports (module level):
```python
_twilio_client = TwilioClient(
    settings.twilio_api_key_sid,
    settings.twilio_api_key_secret,
    account_sid=settings.twilio_account_sid,
)
```

Add request model and route:
```python
class OutboundCallRequest(BaseModel):
    to: str
    greeting: str = "Hey, this is Bob calling. How are you?"


@app.post("/calls/outbound")
async def outbound_call(body: OutboundCallRequest):
    """Initiate an outbound call via Twilio REST API."""
    twiml_url = f"{settings.public_base_url}/twiml/inbound"
    call = _twilio_client.calls.create(
        to=body.to,
        from_=settings.twilio_phone_number,
        url=twiml_url,
    )
    logger.info("Outbound call initiated: %s → %s", call.sid, body.to)
    return {"call_sid": call.sid, "to": body.to, "status": "initiated"}
```

**Step 4: Run all tests**

```bash
PYTHONPATH=.. pytest tests/ -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/telephony_adapter/
git commit -m "feat: POST /calls/outbound — initiate outbound Twilio calls"
```

---

## Task 6: Wire telephony-adapter into process-manager

The process-manager (`src/process-manager/app.py`) manages services via subprocess. Add telephony-adapter as a managed service.

**Files:**
- Modify: `src/process-manager/app.py`

**Step 1: Read the current SERVICES dict in `src/process-manager/app.py`**

It's at the top of the file. Add a new entry for `telephony`:

```python
TELEPHONY_PYTHON = str(REPO_ROOT / "src/telephony_adapter/venv/bin/python")

SERVICES = {
    "orchestrator": { ... },  # existing
    "client": { ... },        # existing
    "hotkey": { ... },        # existing
    "telephony": {
        "label": "Telephony Adapter",
        "cmd": [
            TELEPHONY_PYTHON, "-m", "uvicorn", "telephony_adapter.main:app",
            "--host", "0.0.0.0", "--port", "8767",
        ],
        "env_extra": {"PYTHONPATH": str(REPO_ROOT / "src")},
        "port": 8767,
    },
}
```

**Step 2: Verify process-manager still starts**

```bash
cd src/process-manager
python3 -c "from app import SERVICES; print(list(SERVICES.keys()))"
```
Expected: `['orchestrator', 'client', 'hotkey', 'telephony']`

**Step 3: Commit**

```bash
git add src/process-manager/app.py
git commit -m "feat: add telephony-adapter to process-manager service registry"
```

---

## Task 7: Add .env credentials + Caddy route

**Step 1: Add missing credentials to `.env`**

The following vars are needed by telephony-adapter config. Add them to `.env` (the file at the repo root):

```
TWILIO_ACCOUNT_SID=AC...        # from Twilio console — Account SID
TWILIO_SECRET=...               # API Key secret paired with TWILIO_SID
TWILIO_PHONE_NUMBER=+1...       # your Twilio phone number
```

`TWILIO_SID` (API Key SID starting with SK) and `ELEVENLABS_VOICE_ID` are already in `.env`.

**Step 2: Add Caddy route on nicolasmac**

SSH to nicolasmac and edit the Caddyfile inside the caddy Docker container. The bcom.myroproductions.com block needs a `/telephony/*` route added that proxies to the Mac Mini (10.0.0.210:8767):

Current bcom block structure:
```
http://bcom.myroproductions.com {
    ...
    root * /app/bcom-c
    file_server
}
```

Add a reverse_proxy handler for /telephony before the file_server directive:
```
http://bcom.myroproductions.com {
    ...
    handle /telephony/* {
        reverse_proxy 10.0.0.210:8767
    }
    root * /app/bcom-c
    file_server
    encode gzip
}
```

To edit the Caddyfile on nicolasmac:
```bash
ssh mini2 "docker exec caddy cat /etc/caddy/Caddyfile" > /tmp/Caddyfile
# Edit /tmp/Caddyfile — add the handle /telephony/* block
scp /tmp/Caddyfile mini2:/tmp/Caddyfile
ssh mini2 "docker cp /tmp/Caddyfile caddy:/etc/caddy/Caddyfile && docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
```

**Step 3: Configure Twilio webhook**

In the Twilio console, set the inbound webhook for your phone number to:
```
https://bcom.myroproductions.com/telephony/twiml/inbound
```
HTTP Method: POST

**Step 4: Verify routing**

```bash
curl https://bcom.myroproductions.com/telephony/health
```
Expected: `{"status":"ok","port":8767}`

**Step 5: Commit**

```bash
git add .env  # only if safe — ensure .env is in .gitignore first
git commit -m "infra: add telephony route to Caddy + Twilio webhook config"
```

Note: **Do not commit secrets to git.** Confirm `.env` is in `.gitignore` before staging it.

---

## Task 8: End-to-end manual test

**Pre-flight checklist:**

1. Start telephony-adapter:
   ```bash
   cd src/telephony_adapter
   source venv/bin/activate
   PYTHONPATH=.. uvicorn telephony_adapter.main:app --host 0.0.0.0 --port 8767
   ```

2. Verify health:
   ```bash
   curl http://localhost:8767/health
   curl https://bcom.myroproductions.com/telephony/health
   ```

3. Verify TwiML:
   ```bash
   curl -X POST https://bcom.myroproductions.com/telephony/twiml/inbound
   ```
   Expected: XML response containing `<ConversationRelay` and `ElevenLabs`

**Inbound call test:**
- Call your Twilio phone number from any phone
- Bob should answer with the welcome greeting (spoken by ElevenLabs via ConversationRelay)
- Speak a question — Bob should respond via Claude

**Outbound call test:**
```bash
curl -X POST http://localhost:8767/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{"to": "+1YOUR_MOBILE_NUMBER"}'
```
- Your phone should ring
- Answer it — Bob greets you and you can have a conversation

**Step 1: Commit final state**

```bash
git add src/telephony_adapter/ src/process-manager/app.py
git commit -m "feat: Phase 2 complete — Twilio ConversationRelay + ElevenLabs telephony"
```

---

## ADR to write after completion

Write `docs/adr/ADR-010-twilio-conversationrelay-elevenlabs-telephony.md` covering:
- Why ConversationRelay over raw Media Streams (lower complexity, native ElevenLabs integration)
- Why telephony-adapter is a separate service (isolated per-call sessions, doesn't share orchestrator state)
- Caddy /telephony/* routing decision
- Twilio API Key auth vs Account SID+AuthToken

---

## Notes for the implementing agent

- **Python package naming:** The directory is `src/telephony_adapter/` (underscore). Always run with `PYTHONPATH=<repo>/src` so `import telephony_adapter` resolves.
- **Twilio auth:** We use an API Key (TWILIO_SID = SK...) + API Key Secret (TWILIO_SECRET) + Account SID. This is the recommended auth pattern over Account SID + AuthToken.
- **ElevenLabs voice format in TwiML:** Start with the raw voice ID. If you need to add model/speed params, the format is `{voiceId}-{model}-{speed}_{stability}_{similarity}` — verify against Twilio docs before using.
- **ConversationRelay `last` flag:** The final text message sent to Twilio must have `"last": true`. Twilio buffers all tokens until it sees `last: true` then sends the full text to ElevenLabs for synthesis. Stream Claude tokens but only mark the final empty token as `last: true`.
- **Working directory:** All commands run from the repo root `/Volumes/DevDrive-M4Pro/Projects/BCOM-C-Feature/` unless otherwise specified.
- **Branch:** `bob/phase2-twilio-telephony`
