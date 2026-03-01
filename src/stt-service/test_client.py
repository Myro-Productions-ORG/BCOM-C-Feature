"""Quick test client for the STT WebSocket server.

Usage:
    python test_client.py path/to/audio.wav
    python test_client.py path/to/audio.raw   # raw PCM 16kHz mono int16

Connects to the STT server, sends the audio, prints transcription.
"""

import asyncio
import json
import sys
import wave

import websockets

SERVER_URL = "ws://10.0.0.10:8765/ws/transcribe"
CHUNK_SIZE = 8192  # bytes per send


def load_wav(path: str) -> bytes:
    with wave.open(path, "rb") as wf:
        assert wf.getnchannels() == 1, "Must be mono"
        assert wf.getsampwidth() == 2, "Must be 16-bit"
        assert wf.getframerate() == 16000, "Must be 16kHz"
        return wf.readframes(wf.getnframes())


def load_raw(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


async def test_transcribe(audio_path: str):
    if audio_path.endswith(".wav"):
        audio = load_wav(audio_path)
    else:
        audio = load_raw(audio_path)

    print(f"Audio: {len(audio)} bytes ({len(audio) / 32000:.1f}s at 16kHz)")

    async with websockets.connect(SERVER_URL) as ws:
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready"
        print("Connected to STT server.")

        # Send audio in chunks
        for i in range(0, len(audio), CHUNK_SIZE):
            chunk = audio[i : i + CHUNK_SIZE]
            await ws.send(chunk)

        # Signal end
        await ws.send(json.dumps({"type": "end"}))

        # Receive results
        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == "segment":
                print(f"  [{msg['start']:.1f}s - {msg['end']:.1f}s] {msg['text']}")
            elif msg["type"] == "final":
                print(f"\nFinal: {msg['text']}")
                print(f"Duration: {msg['duration']}s | Processing: {msg['processing_ms']}ms")
                break
            elif msg["type"] == "error":
                print(f"Error: {msg['message']}")
                break


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_client.py <audio_file>")
        sys.exit(1)
    asyncio.run(test_transcribe(sys.argv[1]))
