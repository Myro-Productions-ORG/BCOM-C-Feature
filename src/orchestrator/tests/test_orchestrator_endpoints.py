"""Tests for the new orchestrator settings endpoints."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("orchestrator.config.OrchestratorConfig") as mock_cfg_cls:
        mock_cfg_cls.return_value = MagicMock(
            port=8766,
            stt_url="ws://127.0.0.1:8765/ws/transcribe",
            claude_model="claude-haiku-4-5-20251001",
            claude_temperature=0.6,
            output_device="",
            anthropic_api_key="sk-test",
            elevenlabs_api_key="el-test",
            elevenlabs_voice_id="voice-test",
        )
        from orchestrator.main import app
        return TestClient(app)


def test_settings_endpoint_updates_temperature(client):
    import orchestrator.main as m
    mock_session = MagicMock()
    mock_session._temperature = 0.8
    mock_session._max_tokens = 512
    mock_session._model = "claude-haiku-4-5-20251001"
    m.session = mock_session

    resp = client.post("/settings", json={"temperature": 0.8})
    assert resp.status_code == 200
    mock_session.set_params.assert_called_once_with(temperature=0.8, max_tokens=None, model=None)


def test_settings_endpoint_partial(client):
    import orchestrator.main as m
    mock_session = MagicMock()
    mock_session._temperature = 0.6
    mock_session._max_tokens = 256
    mock_session._model = "claude-haiku-4-5-20251001"
    m.session = mock_session

    resp = client.post("/settings", json={"max_tokens": 256})
    assert resp.status_code == 200
    mock_session.set_params.assert_called_once_with(temperature=None, max_tokens=256, model=None)


def test_clear_memory_endpoint(client):
    import orchestrator.main as m
    mock_session = MagicMock()
    m.session = mock_session

    resp = client.post("/clear-memory")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True
    mock_session.clear_history.assert_called_once()


def test_settings_no_session_returns_503(client):
    import orchestrator.main as m
    m.session = None

    resp = client.post("/settings", json={"temperature": 0.5})
    assert resp.status_code == 503
