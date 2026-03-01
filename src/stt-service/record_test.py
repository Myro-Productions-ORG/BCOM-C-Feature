"""Record a short test clip from your mic and save as WAV.

Usage:
    python record_test.py              # records 5 seconds
    python record_test.py 10           # records 10 seconds

Saves to test_recording.wav (16kHz mono 16-bit).
Requires: pip install pyaudio
"""

import sys
import wave
import pyaudio

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 5
RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024
OUTPUT = "test_recording.wav"

pa = pyaudio.PyAudio()
stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

print(f"Recording {DURATION}s... speak now!")
frames = [stream.read(CHUNK) for _ in range(int(RATE / CHUNK * DURATION))]
print("Done.")

stream.stop_stream()
stream.close()
pa.terminate()

with wave.open(OUTPUT, "wb") as wf:
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(pa.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))

print(f"Saved to {OUTPUT} ({DURATION}s, 16kHz mono)")
