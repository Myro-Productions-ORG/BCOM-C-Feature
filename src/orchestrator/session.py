"""Session state machine: IDLE → LISTENING → THINKING → SPEAKING → loop."""

import enum
import logging
from typing import Callable, Awaitable

import anthropic

from .player import AudioPlayer
from .providers.types import TTSProvider, STTProvider

logger = logging.getLogger(__name__)


class SessionState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class Session:
    def __init__(
        self,
        stt: STTProvider,
        tts: TTSProvider,
        notify: Callable[[str], Awaitable[None]],
        system_prompt: str,
        model: str,
        temperature: float,
        output_device: str = "",
        sample_rate: int = 22050,
    ):
        self._stt = stt
        self._tts = tts
        self._notify = notify
        self._system_prompt = system_prompt
        self._model = model
        self._temperature = temperature
        self._player = AudioPlayer(sample_rate=sample_rate, device=output_device)
        self._client = anthropic.AsyncAnthropic()
        self._history: list[dict] = []
        self._state = SessionState.IDLE
        self._on_state_change: Callable[[SessionState], None] | None = None
        self._max_turns: int | None = None  # None = run forever

    def _set_state(self, state: SessionState) -> None:
        self._state = state
        if self._on_state_change:
            self._on_state_change(state)
        logger.info("Session state: %s", state.value)

    def signal_barge_in(self) -> None:
        """Called by the control WebSocket handler when the client sends barge_in."""
        logger.info("Barge-in received — stopping TTS")
        self._player.stop()

    async def run(self) -> None:
        await self._stt.connect()
        self._set_state(SessionState.IDLE)
        turns = 0

        try:
            while True:
                if self._max_turns is not None and turns >= self._max_turns:
                    break

                # --- LISTENING ---
                self._set_state(SessionState.LISTENING)
                transcript = await self._stt.receive_transcript()
                if not transcript:
                    continue

                logger.info("User said: %s", transcript)
                self._history.append({"role": "user", "content": transcript})

                # --- THINKING ---
                self._set_state(SessionState.THINKING)
                response_text = await self._call_claude()
                self._history.append({"role": "assistant", "content": response_text})
                logger.info("Bob: %s", response_text)

                # --- SPEAKING ---
                self._set_state(SessionState.SPEAKING)
                await self._notify("tts_start")
                await self._player.play(self._tts.synthesize_stream(response_text))
                await self._notify("tts_stop")

                turns += 1
        finally:
            await self._stt.close()

    async def _call_claude(self) -> str:
        """Call Claude with async streaming and return the full response text."""
        full_text = ""
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=1024,
            temperature=self._temperature,
            system=self._system_prompt,
            messages=self._history,
        ) as stream:
            async for event in stream:
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    full_text += event.delta.text
        return full_text.strip()
