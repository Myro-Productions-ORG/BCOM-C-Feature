"""STT WebSocket server.

Accepts audio over WebSocket, runs FasterWhisper + Silero VAD,
returns transcription results as JSON.

Protocol:
  Client sends:
    - Binary frames: raw PCM audio (16kHz, mono, int16 LE)
    - Text frame '{"type": "end"}' to signal end of utterance
    - Text frame '{"type": "ping"}' for keepalive

  Server sends:
    - '{"type": "segment", ...}' for each decoded segment (streaming)
    - '{"type": "final", "text": ..., "segments": [...]}' when utterance is complete
    - '{"type": "error", "message": ...}' on errors
    - '{"type": "ready"}' on connection open
    - '{"type": "pong"}' in response to ping
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

from config import settings
from transcriber import Transcriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

transcriber = Transcriber()


@asynccontextmanager
async def lifespan(app: FastAPI):
    transcriber.load()
    logger.info("STT service ready on %s:%d", settings.host, settings.port)
    yield
    logger.info("STT service shutting down.")


app = FastAPI(title="Bob STT Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": settings.model_size,
        "device": settings.device,
        "compute_type": settings.compute_type,
    }


@app.websocket("/ws/transcribe")
async def websocket_transcribe(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"type": "ready"})
    logger.info("Client connected.")

    audio_buffer = bytearray()

    try:
        while True:
            message = await ws.receive()

            if "bytes" in message and message["bytes"]:
                audio_buffer.extend(message["bytes"])

            elif "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})

                elif msg_type == "end":
                    if len(audio_buffer) == 0:
                        await ws.send_json({
                            "type": "final",
                            "text": "",
                            "segments": [],
                            "duration": 0.0,
                            "processing_ms": 0,
                        })
                        continue

                    audio_bytes = bytes(audio_buffer)
                    audio_buffer.clear()

                    t0 = time.perf_counter()

                    # Run transcription in thread pool to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, transcriber.transcribe_audio, audio_bytes
                    )

                    processing_ms = round((time.perf_counter() - t0) * 1000)

                    # Send individual segments first (for partial display)
                    for seg in result["segments"]:
                        await ws.send_json({"type": "segment", **seg})

                    # Then send final combined result
                    await ws.send_json({
                        "type": "final",
                        "text": result["text"],
                        "segments": result["segments"],
                        "language": result["language"],
                        "duration": result["duration"],
                        "processing_ms": processing_ms,
                    })

                    logger.info(
                        "Transcribed %.1fs audio in %dms: %s",
                        result["duration"],
                        processing_ms,
                        result["text"][:80],
                    )

                elif msg_type == "clear":
                    audio_buffer.clear()
                    await ws.send_json({"type": "cleared"})

    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
