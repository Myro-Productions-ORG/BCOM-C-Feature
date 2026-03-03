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
