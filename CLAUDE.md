# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

**BCOM-C-Feature** is a fork of the BCOM-C operator dashboard, extended with **Bob** — a cascading voice assistant pipeline (STT → LLM → TTS). The dashboard is vanilla HTML/CSS/JS (no framework, no build step). Bob's pipeline is Python (FastAPI STT service) + Rust (desktop mic client).

This fork is isolated from the parent BCOM-C repo's CI/CD webhooks. Changes here do **not** auto-sync to the main dashboard nodes.

---

## Infrastructure

| Machine | IP | Role |
|---|---|---|
| M4 Pro Mac Mini | 10.0.0.210 | Dev machine — you are here |
| Linux Desktop | 10.0.0.10 | RTX 4070 — runs STT service on port 8765 |
| DGX Spark | 10.0.0.69 | 70B LLM orchestrator (port 9010) |

---

## STT Service (Python — Linux Desktop)

Source: `src/stt-service/` — FasterWhisper large-v3-turbo + Silero VAD, FastAPI WebSocket server.

**Setup (run on Linux Desktop 10.0.0.10):**
```bash
cd src/stt-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server.py   # downloads model on first run (~1.5GB to ~/.cache/huggingface/)
```

**Managed as systemd on the Linux Desktop:**
```bash
sudo systemctl status bob-stt
sudo systemctl restart bob-stt   # required after code changes
sudo journalctl -u bob-stt -f
```

Deploy code changes: `scp` the files, then restart the service. No CI/CD pipeline to this box.

**Health check:** `curl http://10.0.0.10:8765/health`

**Config** — all via `STT_*` env vars (see `src/stt-service/config.py`). Key defaults: model `large-v3-turbo`, device `cuda`, port `8765`.

**WebSocket protocol** (`ws://...:8765/ws/transcribe`):
- Client sends binary PCM (16kHz mono int16 LE) + text `{"type":"end"}` to trigger transcription
- Server responds with `{"type":"segment",...}` per segment then `{"type":"final","text":"...","processing_ms":N}`

---

## Desktop Client (Rust — Mac)

Source: `src/desktop-client/` — cpal mic capture → energy VAD → WebSocket STT → JSON on stdout.

```bash
cd src/desktop-client

# Build
cargo build

# List audio devices
cargo run -- devices

# Start listening (requires SSH tunnel, see below)
cargo run -- listen

# Override STT endpoint (e.g., Linux-to-Linux without tunnel)
cargo run -- listen --stt-endpoint ws://10.0.0.10:8765/ws/transcribe
```

**SSH tunnel required on Mac** (ADR-008): macOS Network Extension framework blocks unsigned Rust binaries from reaching external TCP hosts (`EHOSTUNREACH`). The fix is a launchd SSH tunnel forwarding `127.0.0.1:8765` → `linux-desktop:8765`.

```bash
# Install once per Mac
cp infra/mac/com.myroproductions.stt-tunnel.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.myroproductions.stt-tunnel.plist
```

Requires `~/.ssh/id_ed25519` authorized on `myroproductions@10.0.0.10`. The default endpoint in `main.rs` is already `ws://127.0.0.1:8765/ws/transcribe`.

---

## Dashboard Frontend

Source: `index.html`, `assets/`, `pages/` — no build step. Edit files and they are immediately live (Caddy serves them directly from the project directory).

Pages: `orchestrator.html`, `data-gen.html`, `pipeline.html`, `resources.html`, `reports.html`, `settings.html`.

Shared assets:
- `assets/css/bcom.css` — color variables, gauge styles, layout
- `assets/js/bcom.js` — polling engine (5s interval to `/api/metrics`), gauge renderers, clock
- `assets/js/bcom-terminal.js` — xterm.js WebSocket PTY terminal (wss://bcom.myroproductions.com/api/terminal/ws)

**Backend API** (proxied via Caddy): BobSpark-APIs on DGX Spark at `http://10.0.0.69:9010`. Expected `GET /api/metrics` shape is documented in README.md.

---

## CI/CD (parent dashboard, not Bob)

Push to `main` → GitHub Actions (`.github/workflows/deploy.yml`) pulls to three self-hosted nodes in parallel:
- `dgx` runner → `/home/nmyers/Projects/BCOM-C`
- `m4pro` runner → `/Users/myro-pro/Projects/BCOM-C`
- `linux-desktop` runner → `/home/myroproductions/Projects/BCOM-C`

**Note:** These sync to the BCOM-C checkout paths, not BCOM-C-Feature. Bob development here does not trigger those webhooks.

---

## Architecture Decisions

Key decisions are in `docs/adr/`:
- **ADR-001** — Vanilla JS, no framework
- **ADR-006** — Cascading pipeline (STT + LLM + TTS), not end-to-end speech model
- **ADR-007** — STT as systemd daemon on Linux Desktop (not Docker)
- **ADR-008** — launchd SSH tunnel for Mac-to-Linux STT connectivity (unsigned Rust binaries blocked by macOS Network Extensions)

---

## Bob Pipeline Phases

1. **Phase 1 (current):** Local prototype — GPU STT + VAD + Rust desktop client → Anthropic Claude → ElevenLabs TTS
2. **Phase 2:** Twilio ConversationRelay telephony integration
3. **Phase 3:** Webcam vision via Anthropic multimodal
4. **Phase 4:** Latency hardening (TTFT < 500ms target), logging, safety guardrails
