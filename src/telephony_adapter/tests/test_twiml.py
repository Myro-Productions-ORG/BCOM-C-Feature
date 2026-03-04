import xml.etree.ElementTree as ET

import pytest
from httpx import AsyncClient, ASGITransport

from telephony_adapter.twiml import build_conversation_relay_twiml


def test_twiml_contains_conversationrelay():
    xml = build_conversation_relay_twiml(
        ws_url="wss://example.com/telephony/ws/conversation",
        voice_id="testvoiceid",
        greeting="Hello",
    )
    assert "<ConversationRelay" in xml
    assert 'ttsProvider="ElevenLabs"' in xml
    assert "testvoiceid" in xml
    assert "wss://example.com/telephony/ws/conversation" in xml
    assert "Hello" in xml


def test_twiml_is_valid_xml():
    xml = build_conversation_relay_twiml(
        ws_url="wss://example.com/ws",
        voice_id="v123",
        greeting="Hi",
    )
    ET.fromstring(xml)  # raises if invalid XML


def test_twiml_default_greeting():
    xml = build_conversation_relay_twiml(
        ws_url="wss://example.com/ws",
        voice_id="v123",
    )
    assert "Bob" in xml  # default greeting mentions Bob


def test_twiml_escapes_special_chars():
    xml = build_conversation_relay_twiml(
        ws_url='wss://example.com/ws?a=1&b=2',
        voice_id="v123",
        greeting='Say "hi"',
    )
    ET.fromstring(xml)  # must still be valid XML after escaping
    assert "&amp;" in xml   # & in URL is escaped
    assert "&quot;" in xml  # " in greeting is escaped


@pytest.mark.asyncio
async def test_inbound_webhook_returns_xml():
    from telephony_adapter.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/twiml/inbound")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "<ConversationRelay" in resp.text
    assert 'ttsProvider="ElevenLabs"' in resp.text
