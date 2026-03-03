import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock
from starlette.testclient import TestClient

from telephony_adapter.main import app


def test_ws_accepts_connection():
    """WebSocket at /ws/conversation accepts connections."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/conversation") as ws:
            pass  # just connecting and disconnecting is enough


def test_ws_setup_message_accepted():
    """setup message is processed without error — no response expected."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/conversation") as ws:
            ws.send_text(json.dumps({
                "type": "setup",
                "callSid": "CA123",
                "from": "+15550000001",
                "to": "+15550000000",
            }))
            # No response expected for setup — connection stays open


def test_ws_prompt_sends_text_responses():
    """prompt message triggers text responses ending with last=True."""

    async def fake_respond(user_text):
        yield "Hello!", False
        yield "", True

    with patch("telephony_adapter.main.CallSession") as MockSession:
        instance = MagicMock()
        instance.respond = AsyncMock(return_value=fake_respond(""))
        # Make respond return an async generator directly
        async def respond_gen(text):
            yield "Hello!", False
            yield "", True
        instance.respond = respond_gen
        MockSession.return_value = instance

        with TestClient(app) as client:
            with client.websocket_connect("/ws/conversation") as ws:
                ws.send_text(json.dumps({"type": "setup", "callSid": "CA123"}))
                ws.send_text(json.dumps({
                    "type": "prompt",
                    "voicePrompt": "Hello Bob",
                    "last": True,
                }))
                messages = []
                # Collect responses until we get last=True
                for _ in range(10):
                    try:
                        msg = json.loads(ws.receive_text())
                        messages.append(msg)
                        if msg.get("last") is True:
                            break
                    except Exception:
                        break

    assert any(m["type"] == "text" for m in messages)
    assert any(m.get("last") is True for m in messages)


def test_ws_interrupt_is_handled():
    """interrupt message does not crash the handler."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/conversation") as ws:
            ws.send_text(json.dumps({"type": "setup", "callSid": "CA123"}))
            ws.send_text(json.dumps({"type": "interrupt", "utteranceUntilInterrupt": "hey"}))
            # No crash = pass


def test_ws_unknown_message_type_ignored():
    """Unknown message types do not crash the handler."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/conversation") as ws:
            ws.send_text(json.dumps({"type": "setup", "callSid": "CA123"}))
            ws.send_text(json.dumps({"type": "future_message_type", "data": "x"}))
            # No crash = pass
