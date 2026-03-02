"""Queue-based STT provider — transcripts pushed in from control WebSocket."""

import asyncio
import logging

from .types import STTProvider

logger = logging.getLogger(__name__)


class QueueSTTProvider(STTProvider):
    """Receives transcripts from an asyncio.Queue populated by the control WebSocket.

    The Rust desktop client forwards its STT transcripts as
    {"type": "transcript", "text": "..."} messages over /ws/control.
    The main.py control handler puts text into the queue; this provider
    delivers it to the session loop via receive_transcript().
    """

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue

    async def connect(self) -> None:
        logger.info("QueueSTTProvider ready — waiting for transcripts via control channel")

    async def send_audio(self, pcm_bytes: bytes) -> None:
        pass  # Audio is handled entirely by the Rust client

    async def receive_transcript(self) -> str:
        return await self._queue.get()

    async def close(self) -> None:
        pass
