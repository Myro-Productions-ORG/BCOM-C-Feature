"""Bob process manager — web dashboard to start/stop orchestrator and desktop client."""

import asyncio
import json
import os
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = str(REPO_ROOT / "src/orchestrator/venv/bin/python")
RUST_BIN = str(REPO_ROOT / "src/desktop-client/target/release/bob-desktop-client")

SERVICES = {
    "orchestrator": {
        "label": "Orchestrator",
        "cmd": [
            VENV_PYTHON, "-m", "uvicorn", "orchestrator.main:app",
            "--host", "0.0.0.0", "--port", "8766",
        ],
        "env_extra": {"PYTHONPATH": str(REPO_ROOT / "src")},
        "port": 8766,
    },
    "client": {
        "label": "Desktop Client",
        "cmd": [
            RUST_BIN, "listen",
            "--stt-endpoint", "ws://127.0.0.1:8765/ws/transcribe",
            "--orchestrator-url", "ws://127.0.0.1:8766/ws/control",
        ],
        "env_extra": {},
        "port": None,
    },
}

_procs: dict[str, subprocess.Popen | None] = {k: None for k in SERVICES}
_logs: dict[str, deque] = {k: deque(maxlen=400) for k in SERVICES}
_subscribers: dict[str, list[asyncio.Queue]] = {k: [] for k in SERVICES}
_loop: asyncio.AbstractEventLoop | None = None


def _kill_port(port: int) -> None:
    result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
    for pid in result.stdout.strip().split():
        try:
            os.kill(int(pid), 9)
        except Exception:
            pass


def _reader_thread(svc_id: str, proc: subprocess.Popen) -> None:
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            _logs[svc_id].append(line)
            if _loop:
                for q in list(_subscribers[svc_id]):
                    asyncio.run_coroutine_threadsafe(q.put(line), _loop)
    except Exception:
        pass


app = FastAPI()


@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_running_loop()


@app.post("/api/start/{svc_id}")
async def start_service(svc_id: str):
    if svc_id not in SERVICES:
        return {"error": "unknown service"}
    cfg = SERVICES[svc_id]

    # Kill stale process
    proc = _procs[svc_id]
    if proc and proc.poll() is None:
        proc.kill()
        proc.wait()

    if cfg["port"]:
        _kill_port(cfg["port"])

    env = os.environ.copy()
    env.update(cfg["env_extra"])

    new_proc = subprocess.Popen(
        cfg["cmd"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
        env=env,
    )
    _procs[svc_id] = new_proc
    _logs[svc_id].clear()

    threading.Thread(
        target=_reader_thread, args=(svc_id, new_proc), daemon=True
    ).start()

    return {"status": "started", "pid": new_proc.pid}


@app.post("/api/stop/{svc_id}")
async def stop_service(svc_id: str):
    if svc_id not in SERVICES:
        return {"error": "unknown service"}
    proc = _procs[svc_id]
    if proc and proc.poll() is None:
        proc.kill()
        proc.wait()
    _procs[svc_id] = None
    return {"status": "stopped"}


@app.get("/api/status")
async def get_status():
    result = {}
    for svc_id, proc in _procs.items():
        running = proc is not None and proc.poll() is None
        result[svc_id] = {"running": running, "pid": proc.pid if running else None}
    return result


@app.get("/api/stt-health")
async def stt_health():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:8765/health")
            return {"up": r.status_code == 200}
    except Exception:
        return {"up": False}


@app.get("/api/logs/{svc_id}")
async def stream_logs(svc_id: str):
    if svc_id not in SERVICES:
        return StreamingResponse(iter([]), media_type="text/event-stream")

    async def generate() -> AsyncGenerator[str, None]:
        for line in list(_logs[svc_id]):
            yield f"data: {json.dumps(line)}\n\n"

        q: asyncio.Queue = asyncio.Queue()
        _subscribers[svc_id].append(q)
        try:
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(line)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            if q in _subscribers[svc_id]:
                _subscribers[svc_id].remove(q)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BOB CONTROL</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0b0b0b;
  --surface: #111111;
  --surface2: #161616;
  --border: #222222;
  --border2: #2e2e2e;
  --amber: #f59e0b;
  --amber-glow: rgba(245,158,11,0.15);
  --green: #22c55e;
  --green-dim: rgba(34,197,94,0.12);
  --red: #ef4444;
  --red-dim: rgba(239,68,68,0.12);
  --text: #d4d4d4;
  --text-dim: #555;
  --text-mid: #888;
  --log-bg: #080808;
  --log-text: #6b6b6b;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'IBM Plex Mono', monospace;
  min-height: 100vh;
  background-image:
    repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.04) 3px, rgba(0,0,0,0.04) 4px);
}

/* ─── HEADER ─────────────────────────────────────────────────── */
header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 18px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 18px;
}

.logo-mark {
  position: relative;
  width: 34px;
  height: 34px;
}
.logo-mark::before, .logo-mark::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 2px solid var(--amber);
}
.logo-mark::before { transform: rotate(0deg); }
.logo-mark::after { transform: rotate(45deg); inset: 6px; background: var(--amber); }

h1 {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 28px;
  letter-spacing: 0.18em;
  color: var(--amber);
  line-height: 1;
}
h1 .sub {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 300;
  letter-spacing: 0.12em;
  color: var(--text-dim);
  display: block;
  margin-top: 3px;
  text-transform: uppercase;
}

.global-btns {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* ─── BUTTONS ─────────────────────────────────────────────────── */
.btn {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 8px 18px;
  border: 1px solid;
  cursor: pointer;
  background: transparent;
  transition: background 0.1s, color 0.1s, border-color 0.1s;
  white-space: nowrap;
}

.btn:active { transform: translateY(1px); }

.btn-green { color: var(--green); border-color: var(--green); }
.btn-green:hover { background: var(--green); color: #000; }

.btn-red { color: var(--red); border-color: var(--red); }
.btn-red:hover { background: var(--red); color: #fff; }

.btn-amber { color: var(--amber); border-color: var(--amber); font-size: 12px; padding: 10px 22px; }
.btn-amber:hover { background: var(--amber); color: #000; }

.btn-muted { color: var(--text-dim); border-color: var(--border2); font-size: 12px; padding: 10px 22px; }
.btn-muted:hover { background: var(--surface2); border-color: var(--text-mid); color: var(--text); }

.btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* ─── LAYOUT ──────────────────────────────────────────────────── */
main {
  padding: 28px 32px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

/* ─── STATUS BAR ──────────────────────────────────────────────── */
.status-bar {
  grid-column: 1 / -1;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.status-label {
  font-size: 10px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-right: 12px;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-dim);
}

.status-pill.up { border-color: rgba(34,197,94,0.3); color: var(--green); background: var(--green-dim); }
.status-pill.down { border-color: rgba(239,68,68,0.2); color: #f87171; background: var(--red-dim); }

.led {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #333;
  flex-shrink: 0;
}
.led.on {
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
  animation: blink 2.4s ease-in-out infinite;
}
.led.amber { background: var(--amber); box-shadow: 0 0 6px var(--amber); animation: blink 2.4s ease-in-out infinite; }
.led.off { background: #2a2a2a; }

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

/* ─── SERVICE CARDS ───────────────────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.card.running {
  border-color: rgba(34,197,94,0.25);
}

.card-head {
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.svc-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.svc-led {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #2a2a2a;
}
.svc-led.running {
  background: var(--green);
  box-shadow: 0 0 10px rgba(34,197,94,0.5);
  animation: blink 2.4s ease-in-out infinite;
}

.svc-name {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 22px;
  letter-spacing: 0.1em;
  color: var(--text);
  line-height: 1;
}
.svc-state {
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-top: 3px;
}
.svc-state.running { color: var(--green); }
.svc-pid {
  font-size: 10px;
  color: var(--text-dim);
  margin-left: 6px;
}

.card-actions { display: flex; gap: 8px; flex-shrink: 0; }

/* ─── LOG PANE ────────────────────────────────────────────────── */
.log-wrap {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.log-pane {
  height: 380px;
  overflow-y: auto;
  padding: 14px 18px;
  background: var(--log-bg);
  font-size: 10.5px;
  line-height: 1.65;
  color: var(--log-text);
}
.log-pane::-webkit-scrollbar { width: 3px; }
.log-pane::-webkit-scrollbar-thumb { background: #222; }

.log-line { white-space: pre-wrap; word-break: break-all; }
.log-line.err { color: #f87171; }
.log-line.warn { color: #d97706; }
.log-line.info { color: #6b6b6b; }
.log-line.accent { color: var(--amber); }
.log-line.success { color: var(--green); }

.log-empty {
  color: #2a2a2a;
  font-style: italic;
  padding: 6px 0;
}

/* fade at top of log */
.log-wrap::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 28px;
  background: linear-gradient(to bottom, var(--log-bg), transparent);
  pointer-events: none;
  z-index: 1;
}
</style>
</head>
<body>

<header>
  <div class="brand">
    <div class="logo-mark"></div>
    <div>
      <h1>BOB CONTROL <span class="sub">Voice Pipeline — Phase 1</span></h1>
    </div>
  </div>
  <div class="global-btns">
    <button class="btn btn-amber" onclick="startAll()">&#9654; Start All</button>
    <button class="btn btn-muted" onclick="stopAll()">&#9632; Stop All</button>
  </div>
</header>

<main>
  <div class="status-bar">
    <span class="status-label">Status</span>
    <div class="status-pill" id="pill-stt">
      <div class="led off" id="led-stt"></div>
      <span id="txt-stt">STT Tunnel</span>
    </div>
    <div class="status-pill" id="pill-orchestrator">
      <div class="led off" id="led-orchestrator"></div>
      <span id="txt-orchestrator">Orchestrator</span>
    </div>
    <div class="status-pill" id="pill-client">
      <div class="led off" id="led-client"></div>
      <span id="txt-client">Desktop Client</span>
    </div>
  </div>

  <!-- Orchestrator card -->
  <div class="card" id="card-orchestrator">
    <div class="card-head">
      <div class="svc-meta">
        <div class="svc-led" id="svcled-orchestrator"></div>
        <div>
          <div class="svc-name">Orchestrator</div>
          <div class="svc-state" id="state-orchestrator">Stopped <span class="svc-pid" id="pid-orchestrator"></span></div>
        </div>
      </div>
      <div class="card-actions">
        <button class="btn btn-green" onclick="startService('orchestrator')">&#9654; Start</button>
        <button class="btn btn-red" onclick="stopService('orchestrator')">&#9632; Stop</button>
      </div>
    </div>
    <div class="log-wrap">
      <div class="log-pane" id="log-orchestrator"><div class="log-empty">No output yet.</div></div>
    </div>
  </div>

  <!-- Desktop client card -->
  <div class="card" id="card-client">
    <div class="card-head">
      <div class="svc-meta">
        <div class="svc-led" id="svcled-client"></div>
        <div>
          <div class="svc-name">Desktop Client</div>
          <div class="svc-state" id="state-client">Stopped <span class="svc-pid" id="pid-client"></span></div>
        </div>
      </div>
      <div class="card-actions">
        <button class="btn btn-green" onclick="startService('client')">&#9654; Start</button>
        <button class="btn btn-red" onclick="stopService('client')">&#9632; Stop</button>
      </div>
    </div>
    <div class="log-wrap">
      <div class="log-pane" id="log-client"><div class="log-empty">No output yet.</div></div>
    </div>
  </div>
</main>

<script>
const SERVICES = ['orchestrator', 'client'];
const evtSources = {};

function classify(line) {
  const l = line.toLowerCase();
  if (l.includes('error') || l.includes('fatal') || l.includes('traceback') || l.includes('exception')) return 'err';
  if (l.includes('warn') || l.includes('401') || l.includes('403') || l.includes('failed')) return 'warn';
  if (l.includes('ready') || l.includes('startup complete') || l.includes('connected') || l.includes('running on')) return 'success';
  if (l.includes('bob:') || l.includes('transcript') || l.includes('speaking') || l.includes('thinking')) return 'accent';
  return 'info';
}

function appendLog(svcId, line) {
  const pane = document.getElementById('log-' + svcId);
  const empty = pane.querySelector('.log-empty');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = 'log-line ' + classify(line);
  div.textContent = line;
  pane.appendChild(div);

  // Keep max 600 lines
  while (pane.children.length > 600) pane.removeChild(pane.firstChild);

  // Auto-scroll
  pane.scrollTop = pane.scrollHeight;
}

function connectLogs(svcId) {
  if (evtSources[svcId]) { evtSources[svcId].close(); }
  const es = new EventSource('/api/logs/' + svcId);
  es.onmessage = (e) => appendLog(svcId, JSON.parse(e.data));
  evtSources[svcId] = es;
}

function updateStatus(data) {
  for (const [svcId, info] of Object.entries(data)) {
    const card = document.getElementById('card-' + svcId);
    const led = document.getElementById('svcled-' + svcId);
    const stateEl = document.getElementById('state-' + svcId);
    const pidEl = document.getElementById('pid-' + svcId);
    const pill = document.getElementById('pill-' + svcId);
    const pillLed = document.getElementById('led-' + svcId);
    const pillTxt = document.getElementById('txt-' + svcId);

    if (info.running) {
      card.classList.add('running');
      led.classList.add('running');
      stateEl.className = 'svc-state running';
      stateEl.childNodes[0].textContent = 'Running ';
      pidEl.textContent = 'pid ' + info.pid;
      pill.classList.add('up'); pill.classList.remove('down');
      pillLed.className = 'led on';
      pillTxt.textContent = svcId === 'client' ? 'Desktop Client' : 'Orchestrator';
    } else {
      card.classList.remove('running');
      led.classList.remove('running');
      stateEl.className = 'svc-state';
      stateEl.childNodes[0].textContent = 'Stopped ';
      pidEl.textContent = '';
      pill.classList.remove('up'); pill.classList.add('down');
      pillLed.className = 'led off';
      pillTxt.textContent = svcId === 'client' ? 'Desktop Client' : 'Orchestrator';
    }
  }
}

async function updateSttHealth() {
  const pill = document.getElementById('pill-stt');
  const led = document.getElementById('led-stt');
  const txt = document.getElementById('txt-stt');
  try {
    const r = await fetch('/api/stt-health');
    const d = await r.json();
    if (d.up) {
      pill.classList.add('up'); pill.classList.remove('down');
      led.className = 'led on';
      txt.textContent = 'STT Tunnel ✓';
    } else {
      pill.classList.add('down'); pill.classList.remove('up');
      led.className = 'led off';
      txt.textContent = 'STT Tunnel ✗';
    }
  } catch {
    pill.classList.add('down'); pill.classList.remove('up');
    led.className = 'led off';
    txt.textContent = 'STT Tunnel ✗';
  }
}

async function pollStatus() {
  try {
    const r = await fetch('/api/status');
    updateStatus(await r.json());
  } catch {}
}

async function startService(svcId) {
  await fetch('/api/start/' + svcId, { method: 'POST' });
  connectLogs(svcId);
  setTimeout(pollStatus, 800);
}

async function stopService(svcId) {
  await fetch('/api/stop/' + svcId, { method: 'POST' });
  setTimeout(pollStatus, 400);
}

async function startAll() {
  await startService('orchestrator');
  // Small delay so orchestrator is up before client connects
  setTimeout(() => startService('client'), 1500);
}

async function stopAll() {
  await stopService('client');
  await stopService('orchestrator');
}

// Init
SERVICES.forEach(connectLogs);
pollStatus();
updateSttHealth();
setInterval(pollStatus, 3000);
setInterval(updateSttHealth, 10000);
</script>
</body>
</html>
"""


@app.get("/")
async def index():
    return HTMLResponse(HTML)


if __name__ == "__main__":
    import webbrowser
    print("Bob Control starting at http://localhost:7766")
    webbrowser.open("http://localhost:7766")
    uvicorn.run(app, host="127.0.0.1", port=7766, log_level="warning")
