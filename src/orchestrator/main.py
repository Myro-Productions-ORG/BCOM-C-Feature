"""Orchestrator FastAPI app with control WebSocket."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import uvicorn

from .config import settings
from .session import Session, SessionState
from .providers.stt_queue import QueueSTTProvider
from .providers.tts_elevenlabs import ElevenLabsTTSProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Load Bob's clean system prompt
_PROMPT_FILE = Path(__file__).resolve().parents[2] / "docs/steering/bob-system-prompt.txt"
_FALLBACK_PROMPT = "You are Bob. You're calm, warm, and direct. You keep responses concise."
SYSTEM_PROMPT = _PROMPT_FILE.read_text().strip() if _PROMPT_FILE.exists() else _FALLBACK_PROMPT

# Active control WebSocket clients
_control_clients: set[WebSocket] = set()

# Transcripts forwarded from the Rust client via control channel
_transcript_queue: asyncio.Queue[str] = asyncio.Queue()

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
    logger.info(
        "ElevenLabs key: %s...%s  voice: %s",
        settings.elevenlabs_api_key[:12],
        settings.elevenlabs_api_key[-4:],
        settings.elevenlabs_voice_id,
    )
    stt = QueueSTTProvider(queue=_transcript_queue)
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
        anthropic_api_key=settings.anthropic_api_key,
        output_device=settings.output_device,
    )
    _session_task = asyncio.create_task(session.run())
    logger.info("Orchestrator ready — control WS on /ws/control")
    yield
    if _session_task:
        _session_task.cancel()


app = FastAPI(title="Bob Orchestrator", lifespan=lifespan)


@app.post("/toggle-active")
async def toggle_active():
    """Broadcast toggle_active to all connected desktop clients (glasses tap)."""
    await _notify_clients("toggle_active")
    return {"status": "toggled"}


@app.get("/health")
async def health():
    state = session._state.value if session else "not_started"
    return {"status": "ok", "session_state": state}


class SettingsUpdate(BaseModel):
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(None, ge=1, le=4096)
    model: str | None = None
    voice_id: str | None = None


@app.post("/settings")
async def update_settings(body: SettingsUpdate):
    if session is None:
        raise HTTPException(status_code=503, detail="Session not started")
    session.set_params(
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        model=body.model,
    )
    if body.voice_id is not None:
        session._tts._voice_id = body.voice_id
        logger.info("Voice updated: %s", body.voice_id)
    params = session.get_params()
    params["voice_id"] = session._tts._voice_id
    return params


@app.post("/clear-memory")
async def clear_memory():
    if session is None:
        raise HTTPException(status_code=503, detail="Session not started")
    session.clear_history()
    return {"cleared": True}


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
            if msg_type == "transcript":
                text = msg.get("text", "").strip()
                if text:
                    logger.info("Transcript queued: %s", text)
                    await _transcript_queue.put(text)
            elif msg_type == "barge_in" and session:
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
