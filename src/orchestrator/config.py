from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

class OrchestratorConfig(BaseSettings):
    port: int = 8766
    stt_url: str = "ws://127.0.0.1:8765/ws/transcribe"
    claude_model: str = "claude-sonnet-4-6"
    claude_temperature: float = 0.6
    output_device: str = ""  # Empty = sounddevice default; set to "Vivaud" or partial match

    # Shared API keys — read without ORCHESTRATOR_ prefix from .env
    anthropic_api_key: str = Field(
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "ORCHESTRATOR_ANTHROPIC_API_KEY")
    )
    elevenlabs_api_key: str = Field(
        validation_alias=AliasChoices("ELEVENLABS_API_KEY", "ORCHESTRATOR_ELEVENLABS_API_KEY")
    )
    elevenlabs_voice_id: str = Field(
        validation_alias=AliasChoices("ELEVENLABS_VOICE_ID", "ORCHESTRATOR_ELEVENLABS_VOICE_ID")
    )

    model_config = {
        "env_prefix": "ORCHESTRATOR_",
        "env_file": str(_ENV_FILE),
        "extra": "ignore",
    }

# Module-level singleton — tests should patch env vars before importing this module,
# or use importlib.reload(orchestrator.config) to force re-instantiation.
settings = OrchestratorConfig()
