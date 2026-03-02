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
