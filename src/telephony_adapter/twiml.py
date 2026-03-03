"""TwiML response builders for Twilio ConversationRelay."""

import xml.sax.saxutils as saxutils

_DEFAULT_GREETING = "Hey, this is Bob. What can I do for you?"
_QUOTE = {'"': "&quot;"}


def build_conversation_relay_twiml(
    ws_url: str,
    voice_id: str,
    greeting: str = _DEFAULT_GREETING,
) -> str:
    """Return TwiML XML string that activates ConversationRelay with ElevenLabs TTS."""
    safe_url = saxutils.escape(ws_url, _QUOTE)
    safe_voice = saxutils.escape(voice_id, _QUOTE)
    safe_greeting = saxutils.escape(greeting, _QUOTE)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay
      url="{safe_url}"
      ttsProvider="ElevenLabs"
      voice="{safe_voice}"
      welcomeGreeting="{safe_greeting}"
    />
  </Connect>
</Response>"""
