import os

# Set required env vars before any telephony_adapter module is imported.
# TelephonyConfig is instantiated at module level, so these must be in place
# before collection triggers an import.
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_SID", "SKtest")
os.environ.setdefault("TWILIO_SECRET", "testsecret")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15550000000")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "testvoice")
os.environ.setdefault("ELEVENLABS_API_KEY", "el-test")
