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
    mock_response.status_code = 200
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
    mock_response = AsyncMock()
    mock_response.status_code = 401
    mock_response.aread = AsyncMock(return_value=b'{"detail":{"message":"Unauthorized"}}')
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
