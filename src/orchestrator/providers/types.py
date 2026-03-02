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
