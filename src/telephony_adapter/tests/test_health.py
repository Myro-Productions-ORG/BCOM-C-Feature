import pytest
from httpx import AsyncClient, ASGITransport


def test_import():
    from telephony_adapter.main import app
    assert app is not None


@pytest.mark.asyncio
async def test_health():
    from telephony_adapter.main import app
    from telephony_adapter.config import settings
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["port"] == settings.port
