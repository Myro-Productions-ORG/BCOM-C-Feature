# STT Service — FasterWhisper + Silero VAD

WebSocket-based speech-to-text service running on the Linux Desktop (4070 12GB).

## Model

- **FasterWhisper large-v3-turbo** with int8 quantization
- ~4GB VRAM, ~5-6x faster than large-v3
- Silero VAD built-in for speech detection

## Setup (Linux Desktop — 10.0.0.10)

```bash
# Create venv
cd src/stt-service
python3 -m venv venv
source venv/bin/activate

# Install CUDA-enabled faster-whisper
pip install -r requirements.txt

# First run will auto-download the model (~1.5GB)
python server.py
```

The model downloads from HuggingFace on first launch and is cached in `~/.cache/huggingface/`.

## Configuration

All settings via environment variables with `STT_` prefix:

| Variable | Default | Description |
|---|---|---|
| `STT_MODEL_SIZE` | `large-v3-turbo` | Whisper model variant |
| `STT_DEVICE` | `cuda` | `cuda` or `cpu` |
| `STT_COMPUTE_TYPE` | `int8` | `float16`, `int8`, `int8_float16` |
| `STT_LANGUAGE` | `en` | Language code |
| `STT_HOST` | `0.0.0.0` | Server bind address |
| `STT_PORT` | `8765` | Server port |
| `STT_VAD_ENABLED` | `true` | Enable Silero VAD filtering |
| `STT_MIN_SPEECH_DURATION_MS` | `300` | Minimum speech length to keep |
| `STT_MIN_SILENCE_DURATION_MS` | `400` | Silence duration to split segments |
| `STT_MAX_SPEECH_DURATION_S` | `15.0` | Force segment cut after this |

## WebSocket Protocol

**Endpoint:** `ws://10.0.0.10:8765/ws/transcribe`

### Client sends
- **Binary frames:** Raw PCM audio (16kHz, mono, int16 little-endian)
- **Text `{"type": "end"}`:** Signals end of utterance, triggers transcription
- **Text `{"type": "clear"}`:** Clears audio buffer without transcribing
- **Text `{"type": "ping"}`:** Keepalive

### Server responds
- `{"type": "ready"}` — Connection established
- `{"type": "segment", "start": 0.0, "end": 1.5, "text": "..."}` — Per-segment result
- `{"type": "final", "text": "...", "segments": [...], "processing_ms": 150}` — Complete result
- `{"type": "error", "message": "..."}` — Error

## Testing

From the M4 Pro (or any machine on the network):

```bash
# Health check
curl http://10.0.0.10:8765/health

# Send a test WAV file
python test_client.py /path/to/test.wav
```

Test audio must be 16kHz mono 16-bit WAV.

## Network

The service binds to `0.0.0.0:8765` so it's accessible from:
- M4 Pro (10.0.0.210) — desktop client / orchestrator
- DGX Spark (10.0.0.69) — if needed
