from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class TelephonyConfig(BaseSettings):
    port: int = 8767
    public_base_url: str = "https://bcom.myroproductions.com/telephony"

    twilio_account_sid: str = Field(
        validation_alias=AliasChoices("TWILIO_ACCOUNT_SID", "TELEPHONY_TWILIO_ACCOUNT_SID")
    )
    twilio_api_key_sid: str = Field(
        validation_alias=AliasChoices("TWILIO_SID", "TELEPHONY_TWILIO_API_KEY_SID")
    )
    twilio_api_key_secret: str = Field(
        validation_alias=AliasChoices("TWILIO_SECRET", "TELEPHONY_TWILIO_API_KEY_SECRET")
    )
    twilio_phone_number: str = Field(
        validation_alias=AliasChoices("TWILIO_PHONE_NUMBER", "TELEPHONY_TWILIO_PHONE_NUMBER")
    )
    anthropic_api_key: str = Field(
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "TELEPHONY_ANTHROPIC_API_KEY")
    )
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_temperature: float = 0.6
    claude_max_tokens: int = 512
    elevenlabs_voice_id: str = Field(
        validation_alias=AliasChoices("ELEVENLABS_VOICE_ID", "TELEPHONY_ELEVENLABS_VOICE_ID")
    )

    model_config = {
        "env_prefix": "TELEPHONY_",
        "env_file": str(_ENV_FILE),
        "extra": "ignore",
    }


settings = TelephonyConfig()
