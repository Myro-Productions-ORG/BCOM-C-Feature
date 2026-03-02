"""Tests for Session runtime parameter updates."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from orchestrator.session import Session


def _make_session(**kwargs):
    defaults = dict(
        stt=MagicMock(),
        tts=MagicMock(),
        notify=AsyncMock(),
        system_prompt="You are Bob.",
        model="claude-haiku-4-5-20251001",
        temperature=0.6,
        anthropic_api_key="sk-test",
        output_device="",
    )
    defaults.update(kwargs)
    return Session(**defaults)


def test_default_max_tokens():
    s = _make_session()
    assert s._max_tokens == 512


def test_set_params_temperature():
    s = _make_session()
    s.set_params(temperature=0.9)
    assert s._temperature == 0.9


def test_set_params_max_tokens():
    s = _make_session()
    s.set_params(max_tokens=256)
    assert s._max_tokens == 256


def test_set_params_model():
    s = _make_session()
    s.set_params(model="claude-sonnet-4-6")
    assert s._model == "claude-sonnet-4-6"


def test_set_params_partial_update():
    s = _make_session()
    s.set_params(temperature=0.3)
    assert s._temperature == 0.3
    assert s._max_tokens == 512  # unchanged


def test_clear_history():
    s = _make_session()
    s._history = [{"role": "user", "content": "hello"}]
    s.clear_history()
    assert s._history == []
