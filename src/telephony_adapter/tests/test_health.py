import os
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_SID", "SKtest")
os.environ.setdefault("TWILIO_SECRET", "testsecret")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "testvoice")

import pytest
from httpx import AsyncClient, ASGITransport


def test_import():
    from telephony_adapter.main import app
    assert app is not None


@pytest.mark.asyncio
async def test_health():
    from telephony_adapter.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
