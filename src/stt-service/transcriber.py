"""FasterWhisper transcription engine with Silero VAD."""

import io
import logging
import numpy as np
from faster_whisper import WhisperModel
from config import settings

logger = logging.getLogger(__name__)


class Transcriber:
    """Wraps FasterWhisper model with VAD for segment-level transcription."""

    def __init__(self):
        self.model = None

    def load(self):
        logger.info(
            "Loading model=%s device=%s compute=%s",
            settings.model_size,
            settings.device,
            settings.compute_type,
        )
        self.model = WhisperModel(
            settings.model_size,
            device=settings.device,
            compute_type=settings.compute_type,
        )
        logger.info("Model loaded and ready.")

    def transcribe_audio(self, audio_bytes: bytes) -> dict:
        """Transcribe a complete audio segment.

        Args:
            audio_bytes: Raw PCM audio, 16kHz mono int16 little-endian.

        Returns:
            dict with 'text', 'segments', 'language', 'duration'.
        """
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if len(audio_np) == 0:
            return {"text": "", "segments": [], "language": "", "duration": 0.0}

        vad_params = None
        if settings.vad_enabled:
            vad_params = {
                "threshold": settings.vad_threshold,
                "min_speech_duration_ms": settings.min_speech_duration_ms,
                "max_speech_duration_s": settings.max_speech_duration_s,
                "min_silence_duration_ms": settings.min_silence_duration_ms,
                "speech_pad_ms": settings.speech_pad_ms,
            }

        segments_gen, info = self.model.transcribe(
            audio_np,
            language=settings.language,
            beam_size=settings.beam_size,
            vad_filter=settings.vad_enabled,
            vad_parameters=vad_params,
        )

        segments = []
        full_text_parts = []
        for seg in segments_gen:
            segments.append({
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "no_speech_prob": round(seg.no_speech_prob, 4),
            })
            full_text_parts.append(seg.text.strip())

        return {
            "text": " ".join(full_text_parts),
            "segments": segments,
            "language": info.language,
            "duration": round(info.duration, 3),
        }

    def transcribe_stream(self, audio_bytes: bytes):
        """Generator that yields segments as they are decoded.

        Useful for streaming partial results back over WebSocket.
        """
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        if len(audio_np) == 0:
            return

        vad_params = None
        if settings.vad_enabled:
            vad_params = {
                "threshold": settings.vad_threshold,
                "min_speech_duration_ms": settings.min_speech_duration_ms,
                "max_speech_duration_s": settings.max_speech_duration_s,
                "min_silence_duration_ms": settings.min_silence_duration_ms,
                "speech_pad_ms": settings.speech_pad_ms,
            }

        segments_gen, info = self.model.transcribe(
            audio_np,
            language=settings.language,
            beam_size=settings.beam_size,
            vad_filter=settings.vad_enabled,
            vad_parameters=vad_params,
        )

        for seg in segments_gen:
            yield {
                "type": "segment",
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "no_speech_prob": round(seg.no_speech_prob, 4),
            }
