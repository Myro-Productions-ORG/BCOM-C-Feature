"""Telephony adapter — Twilio ConversationRelay + ElevenLabs TTS + Anthropic Claude."""

import json
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
import uvicorn

from .config import settings
from .twiml import build_conversation_relay_twiml
from .call_session import CallSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bob Telephony Adapter")

_active_sessions: dict[str, CallSession] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "port": settings.port}


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

            elif msg_type == "dtmf":
                logger.info(
                    "[%s] DTMF: %s",
                    getattr(session, "call_sid", "?"),
                    msg.get("digit"),
                )

            elif msg_type == "error":
                logger.error("ConversationRelay error: %s", msg)

    except WebSocketDisconnect:
        if session:
            _active_sessions.pop(session.call_sid, None)
            logger.info("ConversationRelay session ended: %s", session.call_sid)


if __name__ == "__main__":
    uvicorn.run(
        "telephony_adapter.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
    )
