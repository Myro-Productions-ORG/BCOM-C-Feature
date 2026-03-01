# tests/orchestrator/test_session.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from orchestrator.providers.types import TTSProvider, STTProvider


class FakeTTS(TTSProvider):
    def __init__(self, chunks=None):
        self.chunks = chunks or [b"\x00\x01" * 100]
        self.called_with = []

    async def synthesize_stream(self, text: str):
        self.called_with.append(text)
        for c in self.chunks:
            yield c


class FakeSTT(STTProvider):
    def __init__(self, transcripts):
        self._transcripts = iter(transcripts)

    async def connect(self): pass
    async def send_audio(self, pcm_bytes): pass
    async def receive_transcript(self):
        return next(self._transcripts)
    async def close(self): pass


@pytest.mark.asyncio
async def test_session_transitions_through_states():
    """Session goes IDLE→LISTENING→THINKING→SPEAKING→LISTENING on a single turn."""
    states_seen = []

    with patch("orchestrator.session.anthropic") as mock_anthropic, \
         patch("orchestrator.session.AudioPlayer") as MockPlayer:

        # Claude returns a simple response
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter([
            MagicMock(type="content_block_delta",
                      delta=MagicMock(type="text_delta", text="Hello there."))
        ]))
        mock_anthropic.Anthropic.return_value.messages.stream.return_value = mock_stream

        MockPlayer.return_value.play = AsyncMock()

        from orchestrator.session import Session, SessionState

        stt = FakeSTT(transcripts=["say hello"])
        tts = FakeTTS()
        notify = AsyncMock()  # control channel notifier

        session = Session(
            stt=stt,
            tts=tts,
            notify=notify,
            system_prompt="You are Bob.",
            model="claude-sonnet-4-6",
            temperature=0.6,
        )

        session._on_state_change = lambda s: states_seen.append(s)

        # Run one turn then stop
        session._max_turns = 1
        await session.run()

    assert SessionState.LISTENING in states_seen
    assert SessionState.THINKING in states_seen
    assert SessionState.SPEAKING in states_seen

@pytest.mark.asyncio
async def test_session_sends_tts_start_stop_signals():
    """notify is called with tts_start before playback and tts_stop after."""
    with patch("orchestrator.session.anthropic") as mock_anthropic, \
         patch("orchestrator.session.AudioPlayer") as MockPlayer:

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.__iter__ = MagicMock(return_value=iter([
            MagicMock(type="content_block_delta",
                      delta=MagicMock(type="text_delta", text="Hi."))
        ]))
        mock_anthropic.Anthropic.return_value.messages.stream.return_value = mock_stream
        MockPlayer.return_value.play = AsyncMock()

        from orchestrator.session import Session

        stt = FakeSTT(transcripts=["hello"])
        tts = FakeTTS()
        notify = AsyncMock()

        session = Session(stt=stt, tts=tts, notify=notify,
                          system_prompt="You are Bob.", model="m", temperature=0.6)
        session._max_turns = 1
        await session.run()

    calls = [c.args[0] for c in notify.call_args_list]
    assert "tts_start" in calls
    assert "tts_stop" in calls
