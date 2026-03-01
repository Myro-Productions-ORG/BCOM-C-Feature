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
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
