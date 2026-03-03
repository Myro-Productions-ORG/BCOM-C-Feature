"""Telephony adapter — Twilio ConversationRelay + ElevenLabs TTS + Anthropic Claude."""

import logging
from fastapi import FastAPI, Request
from fastapi.responses import Response
import uvicorn

from .config import settings
from .twiml import build_conversation_relay_twiml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bob Telephony Adapter")


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


if __name__ == "__main__":
    uvicorn.run(
        "telephony_adapter.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_level="info",
    )
