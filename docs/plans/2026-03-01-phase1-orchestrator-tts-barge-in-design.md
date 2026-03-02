# Phase 1 Design — Orchestrator + TTS Playback + Barge-In

**Date:** 2026-03-01
**Status:** Approved
**Scope:** Phase 1 local prototype completion (no Twilio)

---

## Problem

The STT pipeline is working (ATR mic → Rust desktop client → FasterWhisper → transcript). There is no TTS playback, no orchestrator, and no barge-in capability. The mic picks up speaker output (music, playback) because the Rust client uses a simple energy-based VAD that cannot distinguish human speech from other audio.

**Hardware context:**
- Input: ATR mic (cardioid, USB or XLR)
- Output: Vivaud USB pod mixer → separate speaker system
- Both on separate macOS audio devices — macOS AEC does not engage automatically

---

## Approach

Approach C: Silero VAD + bidirectional control channel between orchestrator and desktop client.

- Silero VAD (already in the STT service) is speech-specific and won't mistake music for voice
- A control WebSocket lets the orchestrator signal TTS state to the desktop client
- During TTS playback the desktop client raises its Silero confidence threshold — only genuine barge-in speech passes through
- No full AEC required for Phase 1; threshold tuning handles the Vivaud bleed

---

## Architecture

```
[ATR Mic]
    │
[Rust Desktop Client]  ←──── control WebSocket ────┐
    │  PCM 16kHz                                    │
    │  STT WebSocket (existing)                     │
    ▼                                               │
[STT Service — FasterWhisper + Silero]         [Python Orchestrator]
    │  transcript                                   │
    └──────────────────────────────────────────────►│
                                                    │◄── Claude API (streaming)
                                                    │
                                               [TTS Adapter]
                                                    │  PCM chunks (streaming)
                                                    ▼
                                          [sounddevice → Vivaud → Speakers]
```

**Session state machine (orchestrator):**
```
IDLE → LISTENING → THINKING → SPEAKING → LISTENING (loop)
                                │
                         barge_in received
                                │
                           LISTENING (immediate)
```

---

## Components

### 1. Python Orchestrator (`src/orchestrator/`)

FastAPI service. The central brain.

**Responsibilities:**
- Maintains session state (IDLE / LISTENING / THINKING / SPEAKING)
- Connects to STT service WebSocket, receives transcripts
- Sends transcripts to Claude API with streaming enabled
- Passes streamed response text to TTS adapter for playback
- Sends `{"type": "tts_start"}` to desktop client when TTS begins
- Sends `{"type": "tts_stop"}` to desktop client when TTS ends naturally
- Receives `{"type": "barge_in"}` from desktop client → cancels TTS immediately, transitions to LISTENING

**Endpoints:**
- `GET /health` — service status + session state
- `WS /ws/control` — desktop client connects here for bidirectional state signals

**Provider pattern (mirrors Ross's approach, in Python):**
- `TTSProvider` ABC — `synthesize_stream(text) -> AsyncIterator[bytes]`
- `STTProvider` ABC — wraps STT WebSocket session
- ElevenLabs and future providers (Kokoro) implement the same interface

**Bob system prompt:**
Loaded from `docs/steering/bob-personality-and-voice.md`. Temperature 0.6.

**Key files:**
```
src/orchestrator/
├── main.py          # FastAPI app, WebSocket /ws/control
├── session.py       # State machine, main conversation loop
├── providers/
│   ├── types.py     # TTSProvider, STTProvider ABCs
│   ├── tts_elevenlabs.py
│   └── stt_bob.py   # Wrapper around existing STT WebSocket
├── config.py        # Pydantic settings (ORCHESTRATOR_ prefix)
└── requirements.txt
```

---

### 2. TTS Adapter (`src/tts-adapter/` → imported as module by orchestrator)

Not a separate service. A Python module called directly from the orchestrator's session loop.

**Responsibilities:**
- Calls ElevenLabs streaming API, receives PCM chunks as they arrive
- Plays chunks through `sounddevice` to the Vivaud output device with minimal buffer
- Exposes `async stop()` — called by orchestrator on barge-in, immediately drains playback queue
- Fires `on_playback_complete` callback when audio ends naturally

**Audio format:**
- ElevenLabs output: PCM 22050Hz or 44100Hz (configured per voice)
- sounddevice playback: matches ElevenLabs output sample rate, output device = Vivaud

**Key files:**
```
src/tts-adapter/
├── player.py        # sounddevice stream, chunk queue, stop()
├── elevenlabs.py    # ElevenLabs streaming client
└── requirements.txt
```

---

### 3. Rust Desktop Client — Control Channel Addition (`src/desktop-client/`)

Additive change only. Existing STT WebSocket path is untouched.

**New behavior:**
- Opens a second WebSocket connection to `ws://localhost:PORT/ws/control` at startup
- Receives `tts_start` → enters **barge-in mode**: Silero confidence threshold raised to 0.85
- Receives `tts_stop` → exits barge-in mode, normal threshold restored
- In barge-in mode: if Silero returns confidence ≥ 0.85 → sends `{"type": "barge_in"}` to orchestrator and forwards the utterance immediately

**VAD upgrade:**
- Replace energy-only `EnergyVad` with continuous Silero scoring
- Audio frames are sent to STT service's Silero endpoint for per-frame confidence
- EnergyVad retained as a pre-filter to avoid unnecessary Silero calls during true silence

**New CLI flag:**
```
--orchestrator-url  ws://localhost:8766/ws/control  (default)
```

---

## Configuration

All via environment variables.

**Orchestrator (`ORCHESTRATOR_` prefix):**
| Variable | Default | Description |
|---|---|---|
| `ORCHESTRATOR_STT_URL` | `ws://127.0.0.1:8765/ws/transcribe` | STT service WebSocket |
| `ORCHESTRATOR_PORT` | `8766` | Control WebSocket port |
| `ORCHESTRATOR_TTS_PROVIDER` | `elevenlabs` | `elevenlabs` or `self-hosted` |
| `ORCHESTRATOR_CLAUDE_MODEL` | `claude-sonnet-4-6` | Anthropic model |
| `ORCHESTRATOR_CLAUDE_TEMPERATURE` | `0.6` | Per bob-personality-and-voice.md |

**ElevenLabs (`ELEVENLABS_` prefix):**
| Variable | Description |
|---|---|
| `ELEVENLABS_API_KEY` | API key |
| `ELEVENLABS_VOICE_ID` | Voice ID (auditioned per bob-personality-and-voice.md) |

---

## Barge-In Flow (detailed)

```
1. Orchestrator transitions to SPEAKING
2. Orchestrator sends {"type": "tts_start"} over /ws/control
3. Rust client raises Silero threshold to 0.85
4. TTS adapter begins streaming ElevenLabs PCM → sounddevice

5a. [Natural end]
    TTS adapter fires on_playback_complete
    Orchestrator sends {"type": "tts_stop"}
    Rust client drops threshold back to normal
    Orchestrator transitions to LISTENING

5b. [Barge-in]
    User speaks — Silero confidence ≥ 0.85 detected by Rust client
    Rust client sends {"type": "barge_in"} to orchestrator
    Orchestrator calls tts_adapter.stop() immediately
    Orchestrator transitions to LISTENING
    Rust client forwards utterance frames to STT WebSocket
    STT transcript arrives → THINKING → SPEAKING (loop continues)
```

---

## What We're Borrowing from Ross (talk-to-claude)

- Provider interface pattern — `TTSProvider` / `STTProvider` ABCs, factory pattern
- Streaming TTS delivery — play chunks as they arrive, don't wait for full synthesis
- `stt-self-hosted.ts` VAD logic — referenced for threshold/timing decisions (our Silero path is more capable)

## What We're Doing Differently

- Python throughout (matches STT service, no TypeScript/Bun required)
- WebSocket STT streaming (not batch REST) — lower latency
- ElevenLabs for TTS voice quality (not Kokoro) for Phase 1
- Customized application, not a packaged plugin — no generality tax
- Silero confidence-based barge-in (not energy threshold only)

---

## Out of Scope (Phase 2)

- Twilio ConversationRelay phone mode
- Room/phone mode switching agent
- Vision (webcam + Anthropic multimodal)
- Kokoro self-hosted TTS (can swap via provider interface later)
