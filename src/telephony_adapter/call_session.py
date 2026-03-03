"""Per-call Claude session with conversation history."""

import logging
from typing import AsyncGenerator, AsyncIterator

import anthropic

from .config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Bob, a calm and direct voice assistant. "
    "Keep responses concise — you are speaking on a phone call. "
    "No lists or markdown. Speak naturally."
)


class CallSession:
    def __init__(
        self,
        call_sid: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.call_sid = call_sid
        self.history: list[dict] = []
        self._model = model if model is not None else settings.claude_model
        self._temperature = temperature if temperature is not None else settings.claude_temperature
        self._max_tokens = max_tokens if max_tokens is not None else settings.claude_max_tokens
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def respond(self, user_text: str) -> AsyncGenerator[tuple[str, bool], None]:
        """Yield (token, is_last) pairs. Final item is always ("", True)."""
        self.history.append({"role": "user", "content": user_text})
        full_response = ""

        async for token in self._stream_claude(self.history):
            full_response += token
            yield token, False

        self.history.append({"role": "assistant", "content": full_response})
        logger.info("[%s] Bob: %s", self.call_sid, full_response)
        yield "", True

    async def _stream_claude(self, history: list[dict]) -> AsyncIterator[str]:
        """Stream text tokens from Claude."""
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            system=SYSTEM_PROMPT,
            messages=history,
        ) as stream:
            async for event in stream:
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    yield event.delta.text
