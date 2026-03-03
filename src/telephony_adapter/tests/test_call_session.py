import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telephony_adapter.call_session import CallSession


def test_call_session_init():
    session = CallSession(call_sid="CA123")
    assert session.call_sid == "CA123"
    assert session.history == []


@pytest.mark.asyncio
async def test_respond_yields_tokens_and_last_flag():
    """respond() yields (token, False) for each token then ("", True) at end."""
    session = CallSession(call_sid="CA123")

    async def fake_stream(_):
        yield "Hello "
        yield "there!"

    with patch.object(session, "_stream_claude", fake_stream):
        results = []
        async for token, is_last in session.respond("Hi Bob"):
            results.append((token, is_last))

    assert results[-1] == ("", True)                    # final sentinel
    assert all(not last for _, last in results[:-1])    # all others False
    full = "".join(t for t, _ in results)
    assert full == "Hello there!"


@pytest.mark.asyncio
async def test_respond_appends_to_history():
    """respond() adds user + assistant turns to history after streaming."""
    session = CallSession(call_sid="CA123")

    async def fake_stream(_):
        yield "Got it."

    with patch.object(session, "_stream_claude", fake_stream):
        async for _ in session.respond("Hello"):
            pass

    assert len(session.history) == 2
    assert session.history[0] == {"role": "user", "content": "Hello"}
    assert session.history[1] == {"role": "assistant", "content": "Got it."}


@pytest.mark.asyncio
async def test_respond_passes_full_history_to_claude():
    """_stream_claude receives the history including the new user message."""
    session = CallSession(call_sid="CA123")
    captured_history = []

    async def spy_stream(history):
        captured_history.extend(history)
        yield "ok"

    with patch.object(session, "_stream_claude", spy_stream):
        async for _ in session.respond("First"):
            pass

    assert captured_history[0] == {"role": "user", "content": "First"}
