import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from telephony_adapter.main import app


@pytest.mark.asyncio
async def test_outbound_call_returns_call_sid():
    """POST /calls/outbound initiates a Twilio call and returns the SID."""
    mock_call = MagicMock()
    mock_call.sid = "CA_outbound_123"

    with patch("telephony_adapter.main._twilio_client") as mock_client:
        mock_client.calls.create.return_value = mock_call
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/calls/outbound", json={"to": "+15550000001"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["call_sid"] == "CA_outbound_123"
    assert data["to"] == "+15550000001"
    assert data["status"] == "initiated"


@pytest.mark.asyncio
async def test_outbound_call_uses_twiml_url():
    """The Twilio call is created with the correct TwiML URL."""
    mock_call = MagicMock()
    mock_call.sid = "CA_test"

    with patch("telephony_adapter.main._twilio_client") as mock_client:
        mock_client.calls.create.return_value = mock_call
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/calls/outbound", json={"to": "+15550000001"})

    assert "/twiml/inbound" in mock_client.calls.create.call_args.kwargs["url"]


@pytest.mark.asyncio
async def test_outbound_call_missing_to_returns_422():
    """POST /calls/outbound without 'to' field returns 422 validation error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/calls/outbound", json={})
    assert resp.status_code == 422
