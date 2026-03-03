"""TwiML response builders for Twilio ConversationRelay."""

_DEFAULT_GREETING = "Hey, this is Bob. What can I do for you?"


def build_conversation_relay_twiml(
    ws_url: str,
    voice_id: str,
    greeting: str = _DEFAULT_GREETING,
) -> str:
    """Return TwiML XML string that activates ConversationRelay with ElevenLabs TTS."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay
      url="{ws_url}"
      ttsProvider="ElevenLabs"
      voice="{voice_id}"
      welcomeGreeting="{greeting}"
    />
  </Connect>
</Response>"""
