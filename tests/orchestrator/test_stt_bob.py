import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_stt_receive_transcript_returns_final_text():
    """receive_transcript() waits for a 'final' message and returns the text."""
    messages = [
        json.dumps({"type": "ready"}),
        json.dumps({"type": "segment", "text": "hel"}),
        json.dumps({"type": "final", "text": "hello world", "processing_ms": 150}),
    ]

    mock_ws = AsyncMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)
    mock_ws.recv = AsyncMock(side_effect=messages)
    mock_ws.send = AsyncMock()

    with patch("orchestrator.providers.stt_bob.websockets.connect", return_value=mock_ws):
        from orchestrator.providers.stt_bob import BobSTTProvider
        provider = BobSTTProvider(url="ws://127.0.0.1:8765/ws/transcribe")
        await provider.connect()
        await provider.send_audio(b"\x00" * 32)
        transcript = await provider.receive_transcript()

    assert transcript == "hello world"
