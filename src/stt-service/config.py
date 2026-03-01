"""STT service configuration."""

from pydantic_settings import BaseSettings


class STTConfig(BaseSettings):
    model_size: str = "large-v3-turbo"
    device: str = "cuda"
    compute_type: str = "int8"
    language: str = "en"
    beam_size: int = 5

    # VAD settings (Silero, built into FasterWhisper)
    vad_enabled: bool = True
    vad_threshold: float = 0.5
    min_speech_duration_ms: int = 300
    max_speech_duration_s: float = 15.0
    min_silence_duration_ms: int = 400
    speech_pad_ms: int = 100

    # Audio format expected from clients
    sample_rate: int = 16000
    channels: int = 1

    # Server
    host: str = "0.0.0.0"
    port: int = 8765

    model_config = {"env_prefix": "STT_"}


settings = STTConfig()
