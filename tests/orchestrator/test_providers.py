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
