# ADR-008: Persistent SSH Tunnel for Mac-to-Linux STT Connectivity

**Status:** Accepted
**Date:** 2026-03-01
**Authors:** Myro Productions

---

## Context

The Bob desktop client (`src/desktop-client`) runs on the Mac Mini M4 Pro (10.0.0.210) and streams audio to the STT service running on the Linux Desktop (10.0.0.10:8765). Both machines are on the same LAN (10.0.0.0/24).

During development it was discovered that Rust binaries compiled locally receive `EHOSTUNREACH` (os error 65) when attempting direct TCP connections to 10.0.0.10, even though system-signed binaries (`nc`, `curl`, `ssh`) reach the same host successfully. The block is at the macOS kernel level — not at pf, not at the Linux firewall (UFW was inactive on the remote), and not a routing table issue.

**Root cause investigation:**
- pf disabled → still fails
- NordVPN uninstalled → still fails
- Tailscale disconnected → still fails
- The Linux machine has UFW inactive and port 8765 bound on `0.0.0.0`
- macOS Network Extension framework (previously loaded by NordVPN NordLynx, potentially residual Tailscale kernel hooks) intercepts `connect()` syscalls from processes without Apple code signatures or recognized entitlements, returning `EHOSTUNREACH` before any packet leaves the machine
- System binaries pass through because they carry Apple's codesign chain

## Decision

Use a **persistent SSH tunnel** managed by a macOS `launchd` agent to forward `127.0.0.1:8765` → `linux-desktop:8765`.

- The tunnel is established by `/usr/bin/ssh` (Apple-signed), which is not subject to Network Extension filtering
- The desktop client connects to `ws://127.0.0.1:8765/ws/transcribe` — loopback traffic is never intercepted
- `launchd` keeps the tunnel alive with `KeepAlive: true` and `ServerAliveInterval: 30`; it auto-restarts on disconnect or crash
- The plist is version-controlled at `infra/mac/com.myroproductions.stt-tunnel.plist`

## Options Considered

**Option A: Properly sign Rust binaries with network entitlements**
- Requires an Apple Developer account and a full codesign + entitlements workflow on every build
- Correct long-term solution for a distributed app; overkill for a local dev tool
- Does not address the residual kernel state from uninstalled VPN software

**Option B: Disable or reconfigure macOS Network Extensions**
- Requires identifying and removing every Network Extension touching the TCP intercept path
- Fragile — reinstalling Tailscale, NordVPN, or any similar tool would break connectivity again
- No upside; increases attack surface by weakening the security posture

**Option C: SSH tunnel via launchd (chosen)**
- Zero change to security posture — no firewall rules opened, no software disabled
- SSH is already authenticated and encrypted; traffic is secure in transit
- Works regardless of which VPN or Network Extension tools are installed
- Single plist file to deploy; survives reboots and login cycles automatically

## Consequences

- **Default STT endpoint** in `src/desktop-client/src/main.rs` is `ws://127.0.0.1:8765/ws/transcribe`
- Any new Mac running this client must install the launchd agent:
  ```
  cp infra/mac/com.myroproductions.stt-tunnel.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.myroproductions.stt-tunnel.plist
  ```
- SSH key (`~/.ssh/id_ed25519`) must be authorized on `myroproductions@linux-desktop`
- The `--stt-endpoint` flag can still override the default for direct connections in environments without the restriction (e.g., Linux-to-Linux)

## References

- ADR-007: STT systemd deployment on Linux Desktop
- `infra/mac/com.myroproductions.stt-tunnel.plist`
