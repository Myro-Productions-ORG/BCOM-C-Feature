import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import numpy as np

@pytest.mark.asyncio
async def test_player_queues_chunks():
    """play() feeds chunks to the output queue."""
    with patch("orchestrator.player.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value.__enter__ = MagicMock(return_value=mock_stream)
        mock_sd.OutputStream.return_value.__exit__ = MagicMock(return_value=False)

        from orchestrator.player import AudioPlayer
        player = AudioPlayer(sample_rate=22050, device="")

        chunks = [b"\x00\x01" * 100, b"\x00\x02" * 100]

        async def fake_stream():
            for c in chunks:
                yield c

        await player.play(fake_stream())
        # stream.write should have been called for each chunk
        assert mock_stream.write.call_count == len(chunks)

@pytest.mark.asyncio
async def test_player_stop_cancels_playback():
    """stop() interrupts in-progress playback."""
    with patch("orchestrator.player.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value.__enter__ = MagicMock(return_value=mock_stream)
        mock_sd.OutputStream.return_value.__exit__ = MagicMock(return_value=False)

        from orchestrator.player import AudioPlayer
        player = AudioPlayer(sample_rate=22050, device="")

        async def slow_stream():
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield b"\x00\x00" * 100

        play_task = asyncio.create_task(player.play(slow_stream()))
        await asyncio.sleep(0.05)
        player.stop()
        await asyncio.wait_for(play_task, timeout=1.0)
        # Should have stopped before all 100 chunks
        assert mock_stream.write.call_count < 100
