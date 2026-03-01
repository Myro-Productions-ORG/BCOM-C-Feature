# Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Python orchestrator, ElevenLabs TTS playback through the Vivaud speakers, and Silero-based barge-in detection to complete the Phase 1 local voice loop.

**Architecture:** The orchestrator (FastAPI) sits between the existing STT service and Claude API, manages session state (IDLE → LISTENING → THINKING → SPEAKING), and drives TTS playback via sounddevice. A bidirectional control WebSocket between the orchestrator and Rust desktop client carries TTS state signals and barge-in events.

**Tech Stack:** Python 3.11+ (FastAPI, httpx, sounddevice, anthropic, pydantic-settings, pytest, pytest-asyncio), Rust (existing codebase + new control.rs module, tokio-tungstenite already in Cargo.toml)

**Reference files:**
- Design doc: `docs/plans/2026-03-01-phase1-orchestrator-tts-barge-in-design.md`
- Bob personality: `docs/steering/bob-personality-and-voice.md`
- Existing STT service: `src/stt-service/` (pattern reference)
- Existing Rust client: `src/desktop-client/src/` (stt.rs pattern for new control.rs)
- `.env` already has `ELEVENLABS_API_KEY` and `ANTHROPIC_API_KEY`

---

## Task 1: Orchestrator scaffold

**Files:**
- Create: `src/orchestrator/requirements.txt`
- Create: `src/orchestrator/config.py`
- Create: `tests/orchestrator/__init__.py`
- Create: `tests/orchestrator/test_config.py`

**Step 1: Create requirements.txt**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
websockets>=13.0
httpx>=0.27.0
sounddevice>=0.5.0
numpy>=1.26.0
anthropic>=0.40.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
```

**Step 2: Write the failing test**

```python
# tests/orchestrator/test_config.py
import os
import pytest
from unittest.mock import patch

def test_config_loads_defaults():
    with patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "test-key",
        "ELEVENLABS_API_KEY": "test-el-key",
        "ELEVENLABS_VOICE_ID": "test-voice",
    }):
        from orchestrator.config import settings
        assert settings.port == 8766
        assert settings.stt_url == "ws://127.0.0.1:8765/ws/transcribe"
        assert settings.claude_model == "claude-sonnet-4-6"
        assert settings.claude_temperature == 0.6

def test_config_reads_env_overrides():
    with patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "test-key",
        "ELEVENLABS_API_KEY": "test-el-key",
        "ELEVENLABS_VOICE_ID": "test-voice",
        "ORCHESTRATOR_PORT": "9000",
        "ORCHESTRATOR_CLAUDE_TEMPERATURE": "0.8",
    }):
        # Re-import forces re-evaluation
        import importlib
        import orchestrator.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.settings.port == 9000
        assert cfg_mod.settings.claude_temperature == 0.8
```

**Step 3: Run to verify it fails**

```bash
cd src/orchestrator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ../..
PYTHONPATH=src pytest tests/orchestrator/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator'`

**Step 4: Write minimal config.py**

```python
# src/orchestrator/config.py
from pydantic_settings import BaseSettings

class OrchestratorConfig(BaseSettings):
    port: int = 8766
    stt_url: str = "ws://127.0.0.1:8765/ws/transcribe"
    claude_model: str = "claude-sonnet-4-6"
    claude_temperature: float = 0.6
    output_device: str = ""   # Empty = sounddevice default; set to "Vivaud" or partial match

    # From .env directly (no prefix)
    anthropic_api_key: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str

    model_config = {"env_prefix": "ORCHESTRATOR_", "env_file": "../../.env", "extra": "ignore"}

settings = OrchestratorConfig()
```

Also create `src/orchestrator/__init__.py` (empty).

**Step 5: Run tests to verify they pass**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_config.py -v
```

Expected: 2 PASSED

**Step 6: Commit**

```bash
git add src/orchestrator/ tests/orchestrator/
git commit -m "feat: orchestrator scaffold — config + venv"
```

---

## Task 2: Provider ABCs

**Files:**
- Create: `src/orchestrator/providers/__init__.py`
- Create: `src/orchestrator/providers/types.py`
- Create: `tests/orchestrator/test_providers.py`

**Step 1: Write the failing test**

```python
# tests/orchestrator/test_providers.py
import pytest
from orchestrator.providers.types import TTSProvider, STTProvider

def test_tts_provider_is_abstract():
    with pytest.raises(TypeError):
        TTSProvider()

def test_stt_provider_is_abstract():
    with pytest.raises(TypeError):
        STTProvider()

def test_tts_provider_interface():
    """Concrete implementation must implement synthesize_stream."""
    class FakeTTS(TTSProvider):
        async def synthesize_stream(self, text: str):
            yield b"audio"

    provider = FakeTTS()
    assert provider is not None

def test_stt_provider_interface():
    """Concrete implementation must implement connect and receive_transcript."""
    class FakeSTT(STTProvider):
        async def connect(self): pass
        async def send_audio(self, pcm_bytes: bytes): pass
        async def receive_transcript(self) -> str: return "hello"
        async def close(self): pass

    provider = FakeSTT()
    assert provider is not None
```

**Step 2: Run to verify fails**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_providers.py -v
```

Expected: `ImportError`

**Step 3: Implement types.py**

```python
# src/orchestrator/providers/types.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class TTSProvider(ABC):
    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Stream PCM audio chunks for the given text."""
        ...

class STTProvider(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Open connection to STT service."""
        ...

    @abstractmethod
    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Send raw PCM bytes (16kHz mono int16 LE)."""
        ...

    @abstractmethod
    async def receive_transcript(self) -> str:
        """Block until a final transcript is available."""
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
```

**Step 4: Run to verify passes**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_providers.py -v
```

Expected: 4 PASSED

**Step 5: Commit**

```bash
git add src/orchestrator/providers/ tests/orchestrator/test_providers.py
git commit -m "feat: orchestrator provider ABCs (TTSProvider, STTProvider)"
```

---

## Task 3: TTS Player (sounddevice chunk queue with stop)

**Files:**
- Create: `src/orchestrator/player.py`
- Create: `tests/orchestrator/test_player.py`

**Step 1: Write the failing test**

```python
# tests/orchestrator/test_player.py
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import numpy as np

@pytest.mark.asyncio
async def test_player_queues_chunks():
    """play() feeds chunks to the output queue."""
    with patch("orchestrator.player.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value.__enter__ = MagicMock(return_value=mock_stream)
        mock_sd.OutputStream.return_value.__exit__ = MagicMock(return_value=False)

        from orchestrator.player import AudioPlayer
        player = AudioPlayer(sample_rate=22050, device="")

        chunks = [b"\x00\x01" * 100, b"\x00\x02" * 100]

        async def fake_stream():
            for c in chunks:
                yield c

        await player.play(fake_stream())
        # stream.write should have been called for each chunk
        assert mock_stream.write.call_count == len(chunks)

@pytest.mark.asyncio
async def test_player_stop_cancels_playback():
    """stop() interrupts in-progress playback."""
    with patch("orchestrator.player.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value.__enter__ = MagicMock(return_value=mock_stream)
        mock_sd.OutputStream.return_value.__exit__ = MagicMock(return_value=False)

        from orchestrator.player import AudioPlayer
        player = AudioPlayer(sample_rate=22050, device="")

        async def slow_stream():
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield b"\x00\x00" * 100

        play_task = asyncio.create_task(player.play(slow_stream()))
        await asyncio.sleep(0.05)
        player.stop()
        await asyncio.wait_for(play_task, timeout=1.0)
        # Should have stopped before all 100 chunks
        assert mock_stream.write.call_count < 100
```

**Step 2: Run to verify fails**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_player.py -v
```

Expected: `ImportError`

**Step 3: Implement player.py**

```python
# src/orchestrator/player.py
"""PCM audio playback via sounddevice with cancellable stop()."""

import asyncio
import logging
from typing import AsyncIterator

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, sample_rate: int = 22050, device: str = ""):
        self._sample_rate = sample_rate
        self._device = device or None   # None = sounddevice default
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Signal playback to stop at the next chunk boundary."""
        self._stop_event.set()

    async def play(self, stream: AsyncIterator[bytes]) -> None:
        """Stream PCM chunks to the output device. Returns when done or stop() called."""
        self._stop_event.clear()
        loop = asyncio.get_event_loop()

        with sd.OutputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            device=self._device,
        ) as out_stream:
            async for chunk in stream:
                if self._stop_event.is_set():
                    logger.info("AudioPlayer: stop() called — interrupting playback")
                    break
                samples = np.frombuffer(chunk, dtype=np.int16)
                # write is blocking — run in thread pool to avoid blocking event loop
                await loop.run_in_executor(None, out_stream.write, samples)
```

**Step 4: Find Vivaud device index at runtime**

Add a helper to `player.py`:

```python
def find_device(name_fragment: str) -> int | None:
    """Return sounddevice index of first output device matching name_fragment (case-insensitive)."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if name_fragment.lower() in dev["name"].lower() and dev["max_output_channels"] > 0:
            return i
    return None
```

**Step 5: Run tests**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_player.py -v
```

Expected: 2 PASSED

**Step 6: Commit**

```bash
git add src/orchestrator/player.py tests/orchestrator/test_player.py
git commit -m "feat: AudioPlayer — sounddevice chunk queue with cancellable stop()"
```

---

## Task 4: ElevenLabs TTS Provider

**Files:**
- Create: `src/orchestrator/providers/tts_elevenlabs.py`
- Create: `tests/orchestrator/test_tts_elevenlabs.py`

**Step 1: Write the failing test**

```python
# tests/orchestrator/test_tts_elevenlabs.py
import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_elevenlabs_streams_chunks():
    """synthesize_stream yields PCM bytes chunks from API response."""
    fake_chunks = [b"\x00\x01" * 50, b"\x00\x02" * 50]

    async def fake_aiter_bytes():
        for c in fake_chunks:
            yield c

    mock_response = MagicMock()
    mock_response.aiter_bytes = fake_aiter_bytes
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=MagicMock(
        __aenter__=AsyncMock(return_value=mock_response),
        __aexit__=AsyncMock(return_value=False),
    ))

    with patch("orchestrator.providers.tts_elevenlabs.httpx.AsyncClient", return_value=mock_client):
        from orchestrator.providers.tts_elevenlabs import ElevenLabsTTSProvider
        provider = ElevenLabsTTSProvider(api_key="test", voice_id="voice123", sample_rate=22050)

        collected = []
        async for chunk in provider.synthesize_stream("Hello Bob"):
            collected.append(chunk)

    assert collected == fake_chunks

@pytest.mark.asyncio
async def test_elevenlabs_raises_on_error():
    """HTTP error from ElevenLabs propagates as exception."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
        "401", request=MagicMock(), response=MagicMock(status_code=401)
    ))

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.stream = MagicMock(return_value=MagicMock(
        __aenter__=AsyncMock(return_value=mock_response),
        __aexit__=AsyncMock(return_value=False),
    ))

    with patch("orchestrator.providers.tts_elevenlabs.httpx.AsyncClient", return_value=mock_client):
        from orchestrator.providers.tts_elevenlabs import ElevenLabsTTSProvider
        provider = ElevenLabsTTSProvider(api_key="test", voice_id="voice123", sample_rate=22050)

        with pytest.raises(httpx.HTTPStatusError):
            async for _ in provider.synthesize_stream("Hello"):
                pass
```

**Step 2: Run to verify fails**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_tts_elevenlabs.py -v
```

Expected: `ImportError`

**Step 3: Implement tts_elevenlabs.py**

```python
# src/orchestrator/providers/tts_elevenlabs.py
"""ElevenLabs streaming TTS provider."""

import logging
from typing import AsyncIterator

import httpx

from .types import TTSProvider

logger = logging.getLogger(__name__)

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self, api_key: str, voice_id: str, sample_rate: int = 22050):
        self._api_key = api_key
        self._voice_id = voice_id
        self._sample_rate = sample_rate

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Stream PCM audio from ElevenLabs as chunks arrive."""
        url = f"{ELEVENLABS_API_BASE}/text-to-speech/{self._voice_id}/stream"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "output_format": f"pcm_{self._sample_rate}",
            "voice_settings": {
                "stability": 0.60,
                "similarity_boost": 0.75,
                "style": 0.35,
                "use_speaker_boost": True,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                logger.info("ElevenLabs TTS stream started")
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_tts_elevenlabs.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add src/orchestrator/providers/tts_elevenlabs.py tests/orchestrator/test_tts_elevenlabs.py
git commit -m "feat: ElevenLabs streaming TTS provider"
```

---

## Task 5: STT Provider Wrapper

**Files:**
- Create: `src/orchestrator/providers/stt_bob.py`
- Create: `tests/orchestrator/test_stt_bob.py`

**Step 1: Write the failing test**

```python
# tests/orchestrator/test_stt_bob.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_stt_receive_transcript_returns_final_text():
    """receive_transcript() waits for a 'final' message and returns the text."""
    messages = [
        json.dumps({"type": "ready"}),
        json.dumps({"type": "segment", "text": "hel"}),
        json.dumps({"type": "final", "text": "hello world", "processing_ms": 150}),
    ]

    mock_ws = AsyncMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)
    mock_ws.recv = AsyncMock(side_effect=messages)
    mock_ws.send = AsyncMock()

    with patch("orchestrator.providers.stt_bob.websockets.connect", return_value=mock_ws):
        from orchestrator.providers.stt_bob import BobSTTProvider
        provider = BobSTTProvider(url="ws://127.0.0.1:8765/ws/transcribe")
        await provider.connect()
        await provider.send_audio(b"\x00" * 32)
        transcript = await provider.receive_transcript()

    assert transcript == "hello world"
```

**Step 2: Run to verify fails**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_stt_bob.py -v
```

Expected: `ImportError`

**Step 3: Implement stt_bob.py**

```python
# src/orchestrator/providers/stt_bob.py
"""WebSocket wrapper for the existing Bob STT service."""

import json
import logging

import websockets

from .types import STTProvider

logger = logging.getLogger(__name__)


class BobSTTProvider(STTProvider):
    def __init__(self, url: str):
        self._url = url
        self._ws = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url)
        # Wait for 'ready'
        msg = await self._ws.recv()
        data = json.loads(msg)
        if data.get("type") != "ready":
            logger.warning("STT: expected 'ready', got %s", data.get("type"))
        logger.info("STT connection ready at %s", self._url)

    async def send_audio(self, pcm_bytes: bytes) -> None:
        if self._ws:
            await self._ws.send(pcm_bytes)

    async def receive_transcript(self) -> str:
        """Read messages until 'final' and return the text."""
        while True:
            raw = await self._ws.recv()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")
            if msg_type == "segment":
                logger.debug("STT segment: %s", msg.get("text", ""))
            elif msg_type == "final":
                text = msg.get("text", "").strip()
                logger.info("STT final: %s (%dms)", text, msg.get("processing_ms", 0))
                return text
            elif msg_type == "error":
                raise RuntimeError(f"STT error: {msg.get('message')}")

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_stt_bob.py -v
```

Expected: 1 PASSED

**Step 5: Commit**

```bash
git add src/orchestrator/providers/stt_bob.py tests/orchestrator/test_stt_bob.py
git commit -m "feat: BobSTTProvider — WebSocket wrapper for STT service"
```

---

## Task 6: Session State Machine

**Files:**
- Create: `src/orchestrator/session.py`
- Create: `tests/orchestrator/test_session.py`

**Step 1: Write the failing test**

```python
# tests/orchestrator/test_session.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from orchestrator.providers.types import TTSProvider, STTProvider


class FakeTTS(TTSProvider):
    def __init__(self, chunks=None):
        self.chunks = chunks or [b"\x00\x01" * 100]
        self.called_with = []

    async def synthesize_stream(self, text: str):
        self.called_with.append(text)
        for c in self.chunks:
            yield c


class FakeSTT(STTProvider):
    def __init__(self, transcripts):
        self._transcripts = iter(transcripts)

    async def connect(self): pass
    async def send_audio(self, pcm_bytes): pass
    async def receive_transcript(self):
        return next(self._transcripts)
    async def close(self): pass


@pytest.mark.asyncio
async def test_session_transitions_through_states():
    """Session goes IDLE→LISTENING→THINKING→SPEAKING→LISTENING on a single turn."""
    states_seen = []

    with patch("orchestrator.session.anthropic") as mock_anthropic, \
         patch("orchestrator.session.AudioPlayer") as MockPlayer:

        # Claude returns a simple response
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter([
            MagicMock(type="content_block_delta",
                      delta=MagicMock(type="text_delta", text="Hello there."))
        ]))
        mock_anthropic.Anthropic.return_value.messages.stream.return_value = mock_stream

        MockPlayer.return_value.play = AsyncMock()

        from orchestrator.session import Session, SessionState

        stt = FakeSTT(transcripts=["say hello"])
        tts = FakeTTS()
        notify = AsyncMock()  # control channel notifier

        session = Session(
            stt=stt,
            tts=tts,
            notify=notify,
            system_prompt="You are Bob.",
            model="claude-sonnet-4-6",
            temperature=0.6,
        )

        session._on_state_change = lambda s: states_seen.append(s)

        # Run one turn then stop
        session._max_turns = 1
        await session.run()

    assert SessionState.LISTENING in states_seen
    assert SessionState.THINKING in states_seen
    assert SessionState.SPEAKING in states_seen

@pytest.mark.asyncio
async def test_session_sends_tts_start_stop_signals():
    """notify is called with tts_start before playback and tts_stop after."""
    with patch("orchestrator.session.anthropic") as mock_anthropic, \
         patch("orchestrator.session.AudioPlayer") as MockPlayer:

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter([
            MagicMock(type="content_block_delta",
                      delta=MagicMock(type="text_delta", text="Hi."))
        ]))
        mock_anthropic.Anthropic.return_value.messages.stream.return_value = mock_stream
        MockPlayer.return_value.play = AsyncMock()

        from orchestrator.session import Session

        stt = FakeSTT(transcripts=["hello"])
        tts = FakeTTS()
        notify = AsyncMock()

        session = Session(stt=stt, tts=tts, notify=notify,
                          system_prompt="You are Bob.", model="m", temperature=0.6)
        session._max_turns = 1
        await session.run()

    calls = [c.args[0] for c in notify.call_args_list]
    assert "tts_start" in calls
    assert "tts_stop" in calls
```

**Step 2: Run to verify fails**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_session.py -v
```

Expected: `ImportError`

**Step 3: Implement session.py**

```python
# src/orchestrator/session.py
"""Session state machine: IDLE → LISTENING → THINKING → SPEAKING → loop."""

import asyncio
import enum
import logging
from typing import Callable, Awaitable

import anthropic

from .player import AudioPlayer
from .providers.types import TTSProvider, STTProvider

logger = logging.getLogger(__name__)


class SessionState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class Session:
    def __init__(
        self,
        stt: STTProvider,
        tts: TTSProvider,
        notify: Callable[[str], Awaitable[None]],
        system_prompt: str,
        model: str,
        temperature: float,
        output_device: str = "",
        sample_rate: int = 22050,
    ):
        self._stt = stt
        self._tts = tts
        self._notify = notify
        self._system_prompt = system_prompt
        self._model = model
        self._temperature = temperature
        self._player = AudioPlayer(sample_rate=sample_rate, device=output_device)
        self._client = anthropic.Anthropic()
        self._history: list[dict] = []
        self._state = SessionState.IDLE
        self._barge_in = asyncio.Event()
        self._on_state_change: Callable[[SessionState], None] | None = None
        self._max_turns: int | None = None  # None = run forever

    def _set_state(self, state: SessionState) -> None:
        self._state = state
        if self._on_state_change:
            self._on_state_change(state)
        logger.info("Session state: %s", state.value)

    def signal_barge_in(self) -> None:
        """Called by the control WebSocket handler when the client sends barge_in."""
        logger.info("Barge-in received — stopping TTS")
        self._player.stop()
        self._barge_in.set()

    async def run(self) -> None:
        await self._stt.connect()
        self._set_state(SessionState.IDLE)
        turns = 0

        try:
            while True:
                if self._max_turns is not None and turns >= self._max_turns:
                    break

                # --- LISTENING ---
                self._barge_in.clear()
                self._set_state(SessionState.LISTENING)
                transcript = await self._stt.receive_transcript()
                if not transcript:
                    continue

                logger.info("User said: %s", transcript)
                self._history.append({"role": "user", "content": transcript})

                # --- THINKING ---
                self._set_state(SessionState.THINKING)
                response_text = await self._call_claude()
                self._history.append({"role": "assistant", "content": response_text})
                logger.info("Bob: %s", response_text)

                # --- SPEAKING ---
                self._set_state(SessionState.SPEAKING)
                await self._notify("tts_start")
                await self._player.play(self._tts.synthesize_stream(response_text))
                await self._notify("tts_stop")

                turns += 1
        finally:
            await self._stt.close()

    async def _call_claude(self) -> str:
        """Call Claude with streaming and return the full response text."""
        full_text = ""
        with self._client.messages.stream(
            model=self._model,
            max_tokens=1024,
            temperature=self._temperature,
            system=self._system_prompt,
            messages=self._history,
        ) as stream:
            for event in stream:
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    full_text += event.delta.text
        return full_text.strip()
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_session.py -v
```

Expected: 2 PASSED

**Step 5: Commit**

```bash
git add src/orchestrator/session.py tests/orchestrator/test_session.py
git commit -m "feat: Session state machine — IDLE/LISTENING/THINKING/SPEAKING loop"
```

---

## Task 7: FastAPI App + Control WebSocket

**Files:**
- Create: `src/orchestrator/main.py`
- Create: `tests/orchestrator/test_main.py`

**Step 1: Write the failing test**

```python
# tests/orchestrator/test_main.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

def test_health_returns_ok():
    with patch("orchestrator.main.settings") as mock_settings, \
         patch("orchestrator.main.Session"):
        mock_settings.port = 8766
        mock_settings.stt_url = "ws://localhost:8765/ws/transcribe"
        mock_settings.anthropic_api_key = "test"
        mock_settings.elevenlabs_api_key = "test"
        mock_settings.elevenlabs_voice_id = "test"
        mock_settings.claude_model = "claude-sonnet-4-6"
        mock_settings.claude_temperature = 0.6
        mock_settings.output_device = ""

        from orchestrator.main import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "session_state" in data
```

**Step 2: Run to verify fails**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_main.py -v
```

Expected: `ImportError`

**Step 3: Implement main.py**

```python
# src/orchestrator/main.py
"""Orchestrator FastAPI app with control WebSocket."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

from .config import settings
from .session import Session, SessionState
from .providers.stt_bob import BobSTTProvider
from .providers.tts_elevenlabs import ElevenLabsTTSProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Load Bob's system prompt from steering doc
import pathlib
_STEERING = pathlib.Path(__file__).parent.parent.parent / "docs/steering/bob-personality-and-voice.md"
SYSTEM_PROMPT = _STEERING.read_text() if _STEERING.exists() else "You are Bob, a warm and caring assistant."

# Active control WebSocket clients
_control_clients: set[WebSocket] = set()

session: Session | None = None
_session_task: asyncio.Task | None = None


async def _notify_clients(msg_type: str) -> None:
    """Broadcast a control message to all connected desktop clients."""
    payload = json.dumps({"type": msg_type})
    disconnected = set()
    for ws in _control_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)
    _control_clients.difference_update(disconnected)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session, _session_task
    stt = BobSTTProvider(url=settings.stt_url)
    tts = ElevenLabsTTSProvider(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.elevenlabs_voice_id,
    )
    session = Session(
        stt=stt,
        tts=tts,
        notify=_notify_clients,
        system_prompt=SYSTEM_PROMPT,
        model=settings.claude_model,
        temperature=settings.claude_temperature,
        output_device=settings.output_device,
    )
    _session_task = asyncio.create_task(session.run())
    logger.info("Orchestrator ready — control WS on /ws/control")
    yield
    if _session_task:
        _session_task.cancel()


app = FastAPI(title="Bob Orchestrator", lifespan=lifespan)


@app.get("/health")
async def health():
    state = session._state.value if session else "not_started"
    return {"status": "ok", "session_state": state}


@app.websocket("/ws/control")
async def control_ws(ws: WebSocket):
    """Bidirectional control channel with the Rust desktop client."""
    await ws.accept()
    _control_clients.add(ws)
    logger.info("Desktop client connected on /ws/control")
    try:
        while True:
            text = await ws.receive_text()
            msg = json.loads(text)
            msg_type = msg.get("type", "")
            if msg_type == "barge_in" and session:
                logger.info("Barge-in signal received from desktop client")
                session.signal_barge_in()
            elif msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        logger.info("Desktop client disconnected from /ws/control")
    finally:
        _control_clients.discard(ws)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, log_level="info")
```

**Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/orchestrator/test_main.py -v
```

Expected: 1 PASSED

**Step 5: Commit**

```bash
git add src/orchestrator/main.py tests/orchestrator/test_main.py
git commit -m "feat: orchestrator FastAPI app + control WebSocket (/ws/control)"
```

---

## Task 8: Rust — Control WebSocket Module

**Files:**
- Create: `src/desktop-client/src/control.rs`
- Modify: `src/desktop-client/src/main.rs` — add `mod control`, `--orchestrator-url` arg, wire into listen loop

**Step 1: Write the test**

```rust
// In src/desktop-client/src/control.rs — add at bottom:
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_control_mode_default() {
        let mode = ControlMode::default();
        assert_eq!(mode, ControlMode::Normal);
    }

    #[test]
    fn test_barge_in_threshold_raised_in_tts_mode() {
        let mode = ControlMode::BargeIn;
        assert!(mode.silero_threshold() > ControlMode::Normal.silero_threshold());
    }
}
```

**Step 2: Run to verify fails**

```bash
cd src/desktop-client
cargo test control -- --nocapture 2>&1 | head -20
```

Expected: `error[E0433]: failed to resolve: use of undeclared module 'control'`

**Step 3: Implement control.rs**

```rust
// src/desktop-client/src/control.rs
//! Bidirectional control channel to the orchestrator.
//!
//! Receives: {"type":"tts_start"} / {"type":"tts_stop"}
//! Sends:    {"type":"barge_in"} / {"type":"ping"}

use anyhow::Result;
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use tokio::sync::watch;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{info, warn};

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub enum ControlMode {
    #[default]
    Normal,
    BargeIn,
}

impl ControlMode {
    /// Silero confidence threshold for speech detection.
    /// Raised during TTS playback so only genuine barge-in triggers.
    pub fn silero_threshold(&self) -> f32 {
        match self {
            ControlMode::Normal => 0.5,
            ControlMode::BargeIn => 0.85,
        }
    }
}

#[derive(Deserialize)]
struct ControlMessage {
    r#type: String,
}

#[derive(Serialize)]
struct OutboundMessage {
    r#type: String,
}

/// Spawns a tokio task that:
/// - Connects to the orchestrator control WebSocket
/// - Updates `mode_tx` when TTS state changes
/// - Sends barge_in when `barge_in_rx` fires
pub async fn run_control_channel(
    url: &str,
    mode_tx: watch::Sender<ControlMode>,
    mut barge_in_rx: tokio::sync::mpsc::Receiver<()>,
) -> Result<()> {
    let (ws_stream, _) = connect_async(url).await?;
    let (mut write, mut read) = ws_stream.split();
    info!("Control channel connected to {}", url);

    loop {
        tokio::select! {
            Some(msg) = read.next() => {
                match msg? {
                    Message::Text(txt) => {
                        if let Ok(ctrl) = serde_json::from_str::<ControlMessage>(&txt) {
                            match ctrl.r#type.as_str() {
                                "tts_start" => {
                                    info!("TTS started — entering barge-in mode");
                                    let _ = mode_tx.send(ControlMode::BargeIn);
                                }
                                "tts_stop" => {
                                    info!("TTS stopped — returning to normal mode");
                                    let _ = mode_tx.send(ControlMode::Normal);
                                }
                                "pong" => {}
                                other => warn!("Unknown control message: {}", other),
                            }
                        }
                    }
                    Message::Close(_) => {
                        warn!("Orchestrator closed control channel");
                        break;
                    }
                    _ => {}
                }
            }
            Some(()) = barge_in_rx.recv() => {
                let msg = serde_json::json!({"type": "barge_in"}).to_string();
                write.send(Message::Text(msg.into())).await?;
                info!("Sent barge_in to orchestrator");
            }
            else => break,
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_control_mode_default() {
        let mode = ControlMode::default();
        assert_eq!(mode, ControlMode::Normal);
    }

    #[test]
    fn test_barge_in_threshold_raised_in_tts_mode() {
        let mode = ControlMode::BargeIn;
        assert!(mode.silero_threshold() > ControlMode::Normal.silero_threshold());
    }
}
```

**Step 4: Run to verify passes**

```bash
cd src/desktop-client
cargo test control -- --nocapture
```

Expected: 2 tests pass

**Step 5: Commit**

```bash
git add src/desktop-client/src/control.rs
git commit -m "feat: Rust control WebSocket module — ControlMode, barge-in signaling"
```

---

## Task 9: Rust — Wire Control Channel + Barge-In Into Listen Loop

**Files:**
- Modify: `src/desktop-client/src/main.rs`

**Step 1: Add `mod control` and `--orchestrator-url` arg to Cli struct**

In `main.rs`, add to the `Listen` subcommand:

```rust
/// Orchestrator control WebSocket URL
#[arg(long, default_value = "ws://127.0.0.1:8766/ws/control")]
orchestrator_url: String,
```

**Step 2: Wire control channel in `run_listen`**

Replace the `run_listen` signature and body with this (full replacement — do not partially edit):

```rust
mod control;

// In Commands::Listen arm, add orchestrator_url to destructure, then:
async fn run_listen(
    stt_endpoint: &str,
    orchestrator_url: &str,
    device: Option<&str>,
    vad_sensitivity: f32,
    silence_ms: u32,
) -> Result<(), anyhow::Error> {
    info!("Bob voice CLI starting");
    info!("STT endpoint: {}", stt_endpoint);
    info!("Orchestrator control: {}", orchestrator_url);

    let (audio_tx, mut audio_rx) = mpsc::unbounded_channel::<Vec<i16>>();
    let _stream = audio::start_capture(device, audio_tx)?;
    info!("Mic capture active. Listening...");

    let stt_client = stt::SttClient::new(stt_endpoint);

    // Control channel — watch for mode changes, channel to send barge-in
    let (mode_tx, mode_rx) = tokio::sync::watch::channel(control::ControlMode::Normal);
    let (barge_in_tx, barge_in_rx) = mpsc::unbounded_channel::<()>();

    // Spawn control channel task (reconnects on failure via outer retry not shown)
    let ctrl_url = orchestrator_url.to_string();
    tokio::spawn(async move {
        if let Err(e) = control::run_control_channel(&ctrl_url, mode_tx, barge_in_rx).await {
            warn!("Control channel error: {}", e);
        }
    });

    let mut vad = EnergyVad::new(
        vad_sensitivity,
        audio::SAMPLE_RATE,
        audio::FRAME_DURATION_MS,
        300,
        silence_ms,
    );

    let mut sample_buf: Vec<i16> = Vec::with_capacity(FRAME_SAMPLES * 2);
    let mut utterance_frames: Vec<Vec<i16>> = Vec::new();
    let mut is_in_utterance = false;

    loop {
        tokio::select! {
            Some(chunk) = audio_rx.recv() => {
                sample_buf.extend_from_slice(&chunk);

                while sample_buf.len() >= FRAME_SAMPLES {
                    let frame: Vec<i16> = sample_buf.drain(..FRAME_SAMPLES).collect();
                    let event = vad.process_frame(&frame);

                    match event {
                        VadEvent::SpeechStart { pre_roll } => {
                            let mode = *mode_rx.borrow();
                            if mode == control::ControlMode::BargeIn {
                                // In barge-in mode: signal orchestrator and proceed
                                info!("Barge-in detected (TTS active)");
                                let _ = barge_in_tx.send(());
                            }
                            info!("Speech detected");
                            is_in_utterance = true;
                            utterance_frames.clear();
                            utterance_frames.extend(pre_roll);
                            utterance_frames.push(frame);
                        }
                        VadEvent::Speech => {
                            if is_in_utterance { utterance_frames.push(frame); }
                        }
                        VadEvent::SpeechEnd => {
                            if is_in_utterance {
                                info!("Speech ended, {} frames captured", utterance_frames.len());
                                is_in_utterance = false;

                                let frames = std::mem::take(&mut utterance_frames);
                                match stt_client.transcribe(frames).await {
                                    Ok(text) if !text.is_empty() => {
                                        let event = TranscriptEvent {
                                            r#type: "final".to_string(),
                                            text: text.clone(),
                                        };
                                        if let Ok(json) = serde_json::to_string(&event) {
                                            println!("{}", json);
                                        }
                                        info!("Transcript: {}", text);
                                    }
                                    Ok(_) => {}
                                    Err(e) => warn!("STT failed: {}", e),
                                }
                            }
                        }
                        VadEvent::Silence => {}
                    }
                }
            }
            _ = tokio::signal::ctrl_c() => {
                info!("Shutting down.");
                break;
            }
        }
    }
    Ok(())
}
```

**Step 3: Build to verify it compiles**

```bash
cd src/desktop-client
cargo build 2>&1
```

Expected: Compiled successfully (warnings ok, no errors)

**Step 4: Run unit tests**

```bash
cargo test
```

Expected: all tests pass

**Step 5: Commit**

```bash
git add src/desktop-client/src/main.rs src/desktop-client/src/control.rs
git commit -m "feat: wire control channel + barge-in into Rust listen loop"
```

---

## Task 10: End-to-End Smoke Test

**Verify the full local loop works: mic → STT → Claude → ElevenLabs → speakers, with barge-in.**

**Step 1: Ensure STT service is running on Linux Desktop**

```bash
# On Linux Desktop (10.0.0.10) — already running as systemd
sudo systemctl status bob-stt
# If not: sudo systemctl start bob-stt
```

Verify: `curl http://10.0.0.10:8765/health` returns `{"status":"ok"}`

**Step 2: Ensure SSH tunnel is active on Mac**

```bash
launchctl list | grep stt-tunnel
# Should show com.myroproductions.stt-tunnel
```

Verify tunnel: `curl http://127.0.0.1:8765/health`

**Step 3: Set env vars and start orchestrator**

```bash
cd src/orchestrator
source venv/bin/activate
export $(cat ../../.env | xargs)
python -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8766 --log-level info
```

Check: `curl http://localhost:8766/health` → `{"status":"ok","session_state":"listening"}`

**Step 4: Start Rust desktop client**

```bash
cd src/desktop-client
cargo run -- listen --orchestrator-url ws://127.0.0.1:8766/ws/control
```

Expected logs:
```
INFO Control channel connected to ws://127.0.0.1:8766/ws/control
INFO Mic capture active. Listening...
```

**Step 5: Speak a test phrase**

Say: "Hey Bob, what's today's date?"

Expected sequence in logs:
- Desktop client: `Speech detected` → `Speech ended` → `Transcript: hey bob what's today's date`
- Orchestrator: `Session state: thinking` → `Session state: speaking` → `tts_start` sent
- Desktop client: `TTS started — entering barge-in mode`
- Audio plays through Vivaud speakers (Bob responds in character)
- Orchestrator: `tts_stop` sent → `Session state: listening`

**Step 6: Test barge-in**

While Bob is speaking, interrupt with a new phrase. Expected:
- Desktop client detects speech during BargeIn mode → sends `barge_in`
- Orchestrator logs: `Barge-in signal received from desktop client`
- Audio cuts off
- Bob processes the new utterance

**Step 7: Commit smoke test notes as ADR**

```bash
# Document any threshold adjustments discovered during smoke test
# in docs/adr/ADR-009-phase1-barge-in-thresholds.md
git add docs/adr/ADR-009-phase1-barge-in-thresholds.md
git commit -m "docs: ADR-009 — Phase 1 barge-in threshold tuning notes"
```

---

## Run All Tests

```bash
# Python
PYTHONPATH=src pytest tests/orchestrator/ -v

# Rust
cd src/desktop-client && cargo test
```

---

## File Map Summary

```
src/orchestrator/
├── __init__.py
├── config.py          (Task 1)
├── player.py          (Task 3)
├── session.py         (Task 6)
├── main.py            (Task 7)
├── providers/
│   ├── __init__.py
│   ├── types.py       (Task 2)
│   ├── tts_elevenlabs.py  (Task 4)
│   └── stt_bob.py     (Task 5)
└── requirements.txt   (Task 1)

src/desktop-client/src/
├── main.rs            (Task 9 — modified)
├── control.rs         (Task 8 — new)
├── audio.rs           (unchanged)
├── stt.rs             (unchanged)
└── vad.rs             (unchanged)

tests/orchestrator/
├── __init__.py
├── test_config.py     (Task 1)
├── test_providers.py  (Task 2)
├── test_player.py     (Task 3)
├── test_tts_elevenlabs.py (Task 4)
├── test_stt_bob.py    (Task 5)
├── test_session.py    (Task 6)
└── test_main.py       (Task 7)
```
