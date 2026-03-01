import importlib
import os
import sys
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock


def test_health_returns_ok():
    env_vars = {
        "ANTHROPIC_API_KEY": "test",
        "ELEVENLABS_API_KEY": "test",
        "ELEVENLABS_VOICE_ID": "test",
    }
    with patch.dict(os.environ, env_vars), \
         patch("orchestrator.providers.stt_bob.BobSTTProvider", autospec=True), \
         patch("orchestrator.providers.tts_elevenlabs.ElevenLabsTTSProvider", autospec=True):

        # Force reload of config and main to pick up patched env and avoid stale module cache
        import orchestrator.config as cfg_mod
        importlib.reload(cfg_mod)

        # Patch Session before importing/reloading main
        with patch("orchestrator.session.Session") as MockSession:
            mock_session_instance = MagicMock()
            mock_session_instance._state.value = "idle"
            mock_session_instance.run = AsyncMock(return_value=None)
            MockSession.return_value = mock_session_instance

            import orchestrator.main as main_mod
            importlib.reload(main_mod)

            client = TestClient(main_mod.app)
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "session_state" in data
