import os
import pytest
from unittest.mock import patch


def test_config_loads_defaults():
    with patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "test-key",
        "ELEVENLABS_API_KEY": "test-el-key",
        "ELEVENLABS_VOICE_ID": "test-voice",
    }):
        from orchestrator.config import settings
        assert settings.port == 8766
        assert settings.stt_url == "ws://127.0.0.1:8765/ws/transcribe"
        assert settings.claude_model == "claude-sonnet-4-6"
        assert settings.claude_temperature == 0.6


def test_config_reads_env_overrides():
    with patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "test-key",
        "ELEVENLABS_API_KEY": "test-el-key",
        "ELEVENLABS_VOICE_ID": "test-voice",
        "ORCHESTRATOR_PORT": "9000",
        "ORCHESTRATOR_CLAUDE_TEMPERATURE": "0.8",
    }):
        import importlib
        import orchestrator.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.settings.port == 9000
        assert cfg_mod.settings.claude_temperature == 0.8
