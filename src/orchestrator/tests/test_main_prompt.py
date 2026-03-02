"""Test that the orchestrator loads the clean system prompt, not the steering doc."""
from pathlib import Path


def test_system_prompt_is_prose_not_markdown():
    prompt_path = Path(__file__).resolve().parents[3] / "docs/steering/bob-system-prompt.txt"
    assert prompt_path.exists(), "bob-system-prompt.txt must exist"
    text = prompt_path.read_text()
    # Must not contain markdown headers
    assert "##" not in text, "System prompt must not contain markdown headers"
    # Must not contain ElevenLabs config noise
    assert "Stability" not in text
    assert "ElevenLabs" not in text
    # Must contain the core identity line
    assert "You are Bob" in text
