# BCOM-C Dashboard

**Bob-AI Command & Control — v0.5**

Operator dashboard for the Bob-AI Pipeline / Data Jet system. Monitors live telemetry from the DGX Spark and Linux desktop nodes, provides system controls, and includes a live remote terminal connected to the DGX Spark via WebSocket/PTY.

---

## What's New in v0.5

- **Live remote terminal** — SHELL tab on every page connects directly to the DGX Spark via xterm.js + WebSocket PTY (wss://bcom.myroproductions.com/api/terminal/ws)
- **Multi-machine CI/CD** — Push to `main` automatically syncs all three nodes (DGX, M4 Pro, Linux Desktop) in parallel via self-hosted GitHub Actions runners
- **Cloudflare tunnel HTTPS** — All pages served over `wss://` with proper mixed-content handling
- **Cache-busting** — `Cache-Control: no-store` on all JS/CSS assets via Caddy

---

## Structure

```
BCOM-C/
├── index.html                   # Main dashboard (SPARK-BOB + LINUX-DSKTP + SHELL)
├── assets/
│   ├── css/bcom.css             # Shared styles — color variables, gauges, layout
│   ├── js/bcom.js               # Shared JS — polling engine, gauge renderers, clock
│   └── js/bcom-terminal.js      # xterm.js terminal — WebSocket PTY, tab wiring
├── pages/
│   ├── orchestrator.html        # AI orchestration control
│   ├── data-gen.html            # Synthetic data pipeline controls
│   ├── pipeline.html            # Ingest / transform / inference routing
│   ├── resources.html           # Model registry, storage, compute allocation
│   └── reports.html             # Run logs, performance history, export
├── docs/
│   └── adr/                     # Architecture Decision Records
│       ├── ADR-001-vanilla-js-no-framework.md
│       ├── ADR-002-caddy-reverse-proxy.md
│       ├── ADR-003-cloudflare-tunnel.md
│       ├── ADR-004-xterm-pty-websocket.md
│       └── ADR-005-self-hosted-runners-cicd.md
└── .github/
    └── workflows/
        └── deploy.yml           # Multi-machine deploy (DGX + M4 Pro + Linux Desktop)
```

---

## Dashboard Panels

**SPARK-BOB** — DGX Spark (NVIDIA GB10, 10.0.0.69)
- CPU / GPU / VRAM load gauges
- CPU temperature bar
- VRAM GB, GPU temp, uptime metrics

**LINUX-DSKTP** — Linux desktop node (10.0.0.10)
- CPU / GPU load gauges
- CPU temperature bar
- RAM GB, uptime metrics

**SHELL** — Live terminal (all pages)
- Connected to DGX Spark via `wss://bcom.myroproductions.com/api/terminal/ws`
- Full PTY: supports `htop`, `vim`, `nano`, interactive bash
- Minimize/restore with state persistence (`localStorage`)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML / CSS / JS — no framework, no build step |
| Terminal | xterm.js v5.3.0 + FitAddon (lazy-loaded from CDN) |
| Reverse proxy | Caddy v2 (Docker) |
| External access | Cloudflare Tunnel → `bcom.myroproductions.com` |
| Backend API | BobSpark-APIs (FastAPI, DGX Spark, port 9010) |
| CI/CD | GitHub Actions self-hosted runners (3 nodes) |

---

## Deployment

The dashboard is deployed automatically on every push to `main` via GitHub Actions. Three self-hosted runners sync in parallel:

| Machine | IP | Runner Label |
|---|---|---|
| DGX Spark | 10.0.0.69 | `dgx` |
| M4 Pro Mac Mini | 10.0.0.210 | `m4pro` |
| Linux Desktop | 10.0.0.10 | `linux-desktop` |

Manual deploy (Mac Mini server):
```bash
# Files are served directly from /Volumes/DevDrive/Projects/websites/BCOM-C
# by Caddy. No build required — edit and it's live.
```

---

## Connecting a Live Data Source

The polling engine polls `/api/metrics` every 5 seconds via Caddy's reverse proxy to BobSpark-APIs.

### Expected API Response — `GET /api/metrics`

```json
{
  "spark": {
    "cpu_pct": 68, "gpu_pct": 74, "vram_pct": 55,
    "vram_gb": "44.2 GB", "gpu_temp": "72°C",
    "cpu_temp": 78, "uptime": "2d 14h"
  },
  "linux": {
    "cpu_pct": 42, "gpu_pct": 31, "cpu_temp": 65,
    "ram_gb": "28.1 GB", "uptime": "5d 3h"
  }
}
```

All fields are optional — missing keys render as `--` without errors.

---

## Architecture Decision Records

Key decisions are documented in [`docs/adr/`](docs/adr/):

- [ADR-001](docs/adr/ADR-001-vanilla-js-no-framework.md) — Vanilla JS, no framework
- [ADR-002](docs/adr/ADR-002-caddy-reverse-proxy.md) — Caddy as reverse proxy
- [ADR-003](docs/adr/ADR-003-cloudflare-tunnel.md) — Cloudflare Tunnel for HTTPS
- [ADR-004](docs/adr/ADR-004-xterm-pty-websocket.md) — xterm.js + PTY WebSocket terminal
- [ADR-005](docs/adr/ADR-005-self-hosted-runners-cicd.md) — Self-hosted CI/CD runners

---

## Bob Voice Assistant (Feature Branch)

This fork adds **Bob**, a multimodal voice assistant that will integrate into the BCOM-C dashboard as a web feature.

**Core loop:** User audio → VAD-gated buffer → GPU STT → Dialog orchestrator (Anthropic Claude) → TTS (ElevenLabs) → output to phone/mic/speaker.

### Modalities
- Voice over phone via Twilio ConversationRelay
- Voice over local mic (desktop/browser/WebRTC)
- Vision via webcam snapshots → Anthropic multimodal (Claude 3)

### Modes
- **Phone agent** — handles inbound/outbound calls, human handoff
- **Companion** — desktop/home lab voice assistant
- **Ops** — tools, MCP, system control (future)

### Bob Directory Structure

```
src/
├── orchestrator/     # Session state, routing, barge-in, tool calls
├── stt-service/      # GPU STT + VAD (FasterWhisper/Silero)
├── tts-adapter/      # ElevenLabs streaming TTS client
├── telephony/        # Twilio Voice + ConversationRelay
├── desktop-client/   # Local mic/speaker capture and playback
├── vision/           # Webcam capture + Anthropic multimodal
├── hooks/            # Integration hooks
└── services/         # Shared service utilities
```

Additional directories: `infra/`, `scripts/`, `tests/`, `experiments/`, `docs/research/`, `docs/steering/`

### Bob Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python (FastAPI / aiohttp) |
| STT | FasterWhisper / WhisperX on DGX/4070 via WebSocket/gRPC |
| TTS | ElevenLabs streaming API |
| Telephony | Twilio ConversationRelay |
| Vision | OpenCV + Anthropic multimodal endpoint |
| LLM | Anthropic Claude (Sonnet/Haiku) streaming API |
| Orchestrator LLM | 70B model on DGX Spark (http://10.0.0.69:9010) |

### Implementation Phases

1. **Phase 1 — Local prototype:** GPU STT + VAD server, CLI mic → STT → Anthropic → ElevenLabs → speakers
2. **Phase 2 — Telephony:** Twilio ConversationRelay integration, session store by call SID
3. **Phase 3 — Vision + tools:** Webcam capture, Anthropic multimodal, tool schemas
4. **Phase 4 — Hardening:** Latency targets (TTFT < 500ms), logging, metrics, safety guardrails

---

*BOB-AI // BCOM-C-Feature v0.6*
