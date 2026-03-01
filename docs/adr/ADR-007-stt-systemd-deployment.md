# ADR-007: STT Service Deployed as systemd Daemon on Linux Desktop

**Status:** Accepted  
**Date:** 2026-02-28  
**Authors:** Myro Productions

---

## Context

The STT service (FasterWhisper large-v3-turbo + Silero VAD) runs on the Linux Desktop (RTX 4070 12GB, 10.0.0.10). It needs to be always-on, auto-start on boot, and recover from crashes without manual intervention.

## Decision

- **Deploy as a systemd service** (`bob-stt.service`) rather than Docker or manual execution.
- Service runs as user `myroproductions`, uses the project venv directly.
- Auto-restarts on failure with 5-second delay.
- Enabled on boot via `multi-user.target`.
- Logs go to journald, accessible via `journalctl -u bob-stt`.

## Rationale

- **systemd is native to Ubuntu 24.04** — zero additional tooling required.
- **Docker adds unnecessary complexity** for a single service on a dedicated GPU box. CUDA passthrough via `nvidia-container-toolkit` is an extra dependency with no real isolation benefit here.
- **tmux/screen** is fragile — doesn't survive reboots or crashes.
- The 4070 is dedicated to STT; no resource contention to isolate against.

## Performance Observed

- Model: large-v3-turbo, int8 quantization, CUDA
- VRAM usage: ~877MB resident
- Cold transcription (first request): ~598ms for 5s audio
- Warm transcription (subsequent): ~174ms for 5s audio
- Speed ratio: ~8x to ~28x real-time

## Consequences

- Code updates require `scp` + `sudo systemctl restart bob-stt` — no CI/CD pipeline to this box yet.
- If we add more GPU services to this machine later, we may revisit Docker Compose for multi-service management.
- The venv path is hardcoded in the service file; moving the project directory requires updating the unit file.

## Management Commands

```bash
sudo systemctl status bob-stt      # Check status
sudo systemctl restart bob-stt     # Restart after code changes
sudo systemctl stop bob-stt        # Stop
sudo journalctl -u bob-stt -f      # Live logs
```
