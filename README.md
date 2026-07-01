# RetroHost

> Self-hosted retro game streaming over WebRTC — no client install required. Open your browser, pick a game, play.

RetroHost turns a Raspberry Pi (or any x86_64 PC) into a local game streaming server. The emulator runs on the server; the browser receives compressed video and sends back input. Same principle as Steam Link — but open source, self-hosted, and works on hardware you already own.

**⚠️ LAN-only by design.** There is no authentication. Never expose RetroHost ports to the internet or deploy on a public cloud server. Read [SECURITY.md](SECURITY.md) before use.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Architecture & Pipeline](#architecture--pipeline)
3. [Performance Metrics](#performance-metrics)
4. [Quick Start — Docker (x86_64)](#quick-start--docker-x8664)
5. [Raspberry Pi Setup](#raspberry-pi-setup)
6. [Configuration Reference](#configuration-reference)
7. [Adding a New Console / Core](#adding-a-new-console--core)
8. [Known Limitations](#known-limitations)
9. [Security Considerations](#security-considerations)
10. [Contributing](#contributing)
11. [Credits](#credits)
12. [License](#license)

---

## How it works

RetroHost is a **server-side emulation streaming** system. The emulator (RetroArch + libretro core) runs headless on the server and writes raw video + audio to a named pipe. FFmpeg reads that pipe, encodes H.264 + Opus, and publishes RTSP to MediaMTX, which delivers the stream to any browser via WebRTC (WHEP). The browser captures keyboard/gamepad input and sends it back over a WebSocket, which the server injects as a virtual input device.

No browser plugin. No client app. No JavaScript framework. Just native browser APIs: `RTCPeerConnection`, `Gamepad API`, `WebSocket`.

---

## Architecture & Pipeline

```
┌─────────────────────────── Server (Pi or x86_64) ─────────────────────────────┐
│                                                                                  │
│  RetroArch (headless, video_driver=null)                                        │
│  writes raw video + PCM audio ──► /tmp/retrohost_av.fifo (Matroska container)  │
│                                            │                                    │
│                                            ▼                                    │
│  ffmpeg                                                                          │
│  reads FIFO, encodes H.264 (hw or sw) + Opus ──► RTSP → 127.0.0.1:8554        │
│                                            │                                    │
│                                            ▼                                    │
│  MediaMTX                                                                        │
│  receives RTSP, serves WHEP (WebRTC) ──────────────────────────────────────┐   │
│                                                                              │   │
│  virtual input device (uinput / SDL2) ◄── WebSocket /ws/input ◄────────┐   │   │
│                                                                          │   │   │
│  FastAPI (port 8000) — orchestrates all of the above                    │   │   │
│                                                                          │   │   │
└──────────────────────────────────────────────────────────────────────────┼───┼───┘
                                                                           │   │
                          Browser ─────────── WebSocket (input) ──────────┘   │
                                  ◄─────────── WebRTC video+audio ────────────┘
```

For a full component-by-component breakdown, design decisions, and replication guide, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Performance Metrics

Measured via `RTCPeerConnection.getStats()` on the client browser.

| Hardware | Encoder | jitter buffer delay | Notes |
|---|---|---|---|
| Raspberry Pi 3 | h264_v4l2m2m (HW) | ~145 ms | Hardware limit; residual input delay ~376 ms |
| x86_64 + NVIDIA RTX 4050 | h264_nvenc (NVENC) | ~93 ms | ~36% lower latency vs Pi 3 |
| x86_64 (no GPU) | libx264 (CPU) | ~120–160 ms | Varies by CPU; functional but heavier load |

Input round-trip (WebSocket send → emulator reaction) is sub-millisecond on the server side; perceived input latency is dominated by the video pipeline delay above.

---

## Quick Start — Docker (x86_64)

**Requirements:** Docker (Engine on Linux, Desktop on Windows/macOS Intel). Architecture must be x86_64 — the build will fail early with a clear message on ARM.

### 1. Clone and build

```bash
git clone <repo-url> retrohost
cd retrohost
docker build -t retrohost .
```

The build compiles PCSX-ReARMed from source (PS1 core) — expect ~10 minutes on first build.

### 2. Run

```bash
# No GPU — works on any machine (libx264 software encoder)
docker run -d --name retrohost --privileged \
  -e RETROHOST_WEBRTC_HOST=<YOUR_LAN_IP> \
  -p 8000:8000 -p 8889:8889 -p 8554:8554 -p 8189:8189/udp \
  -v retrohost-data:/data retrohost

# NVIDIA GPU (NVENC) — requires nvidia-container-toolkit on host
docker run -d --name retrohost --privileged --gpus all \
  -e RETROHOST_WEBRTC_HOST=<YOUR_LAN_IP> \
  -p 8000:8000 -p 8889:8889 -p 8554:8554 -p 8189:8189/udp \
  -v retrohost-data:/data retrohost

# Intel / AMD GPU (VAAPI/QSV)
docker run -d --name retrohost --privileged --device /dev/dri \
  -e RETROHOST_WEBRTC_HOST=<YOUR_LAN_IP> \
  -p 8000:8000 -p 8889:8889 -p 8554:8554 -p 8189:8189/udp \
  -v retrohost-data:/data retrohost
```

> **`RETROHOST_WEBRTC_HOST`** must be the LAN IP of the host machine (e.g. `192.168.1.100`). Without it, WebRTC ICE candidates will advertise the container's internal IP (`172.17.x.x`) and video will not reach other devices on your network.

### 3. Configure storage and play

Open `http://<YOUR_LAN_IP>:8000` in your browser. Click **Configure storage** to point RetroHost to your ROMs (local volume mount or CIFS/Samba network share), then **Scan library**, then click **Play** on any game.

### 4. Transfer a session to another device

When a game is running, any device on the LAN can open the same URL and click **Play here** to receive the stream and take over input. The previous controller is disconnected automatically.

---

## Raspberry Pi Setup

### Prerequisites

- Raspberry Pi 3 or 4 (tested on Pi 3, kernel `6.18.34+rpt-rpi-v7`)
- Raspberry Pi OS Lite (Debian Trixie) — no desktop required
- SSH access with public key authentication

### 1. Install dependencies

```bash
sudo apt-get update
sudo apt-get install -y retroarch ffmpeg python3-venv git cifs-utils
# SNES core example (PS1 is compiled from source — see Adding a New Console)
sudo apt-get install -y libretro-bsnes-mercury-performance
```

### 2. Clone and configure

```bash
git clone <repo-url> ~/retrohost
cd ~/retrohost/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Edit `config/cores.json` to point to your installed core `.so` files:

```json
{
  "ps1": "/home/YOUR_USER/retrohost/emulator/cores/pcsx_rearmed_libretro.so",
  "snes": "/usr/lib/arm-linux-gnueabihf/libretro/bsnes_mercury_performance_libretro.so"
}
```

Place ROMs under `emulator/roms/<console>/` and BIOS files under `emulator/bios/`.

### 3. Run setup scripts (once, idempotent)

```bash
# Configure RetroArch for headless streaming
bash scripts/setup_streaming.sh

# Download MediaMTX binary (ARMv7)
bash scripts/install_mediamtx.sh

# Enable remote input via uinput
bash scripts/setup_input.sh

# (Optional) Enable CIFS/Samba network storage
bash scripts/setup_network_storage.sh
```

### 4. Install and enable systemd services

```bash
# Replace YOUR_USER with your actual username in the .service files first:
# sed -i 's/YOUR_USER/pi/g' scripts/homegames.service scripts/mediamtx.service

sudo cp scripts/mediamtx.service /etc/systemd/system/
sudo cp scripts/homegames.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx homegames
```

### 5. Validate

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/scan
curl http://localhost:8000/games
```

Open `http://<PI_IP>:8000` in your browser.

---

## Configuration Reference

All configuration is via environment variables. Docker defaults are in the `Dockerfile`; Pi defaults are in `backend/app/core/config.py`.

| Variable | Default | Description |
|---|---|---|
| `HOMEGAMES_ROOT` | auto-detected | Root directory of the project |
| `HOMEGAMES_ENCODER` | `h264_v4l2m2m` (Pi) / `auto` (Docker) | Video encoder. `auto` probes nvenc → qsv → vaapi → libx264 |
| `HOMEGAMES_RENDER_NODE` | `/dev/dri/renderD128` | DRM render node for VAAPI/QSV encoders |
| `RETROHOST_WEBRTC_HOST` | _(unset)_ | LAN IP to announce in WebRTC ICE candidates. **Required** for multi-device access |
| `HOMEGAMES_INPUT_PROVIDER` | `uinput` (Pi) / `sdl` (Docker) | Input backend: `uinput` (Linux udev) or `sdl` (SDL2 virtual joystick) |
| `HOMEGAMES_DB_PATH` | `backend/homegames.db` | SQLite database path |
| `HOMEGAMES_STORAGE_CONFIG` | `config/storage.json` | ROM storage config (auto-written by the API) |
| `HOMEGAMES_CIFS_CREDENTIALS` | `/etc/samba/homegames-credentials` | CIFS credential file path (chmod 600) |
| `HOMEGAMES_CIFS_VERS` | `3.0` | SMB protocol version for CIFS mounts |
| `HOMEGAMES_AUDIO_DRIVER` | `pulse` (Docker) / `alsa` (Pi) | RetroArch audio driver |

---

## Adding a New Console / Core

1. Install or compile the libretro core `.so` for the target console.
2. Add an entry to `config/cores.json`:
   ```json
   {
     "ps1": "/path/to/pcsx_rearmed_libretro.so",
     "snes": "/path/to/bsnes_mercury_performance_libretro.so",
     "gba": "/path/to/mgba_libretro.so"
   }
   ```
3. Add the valid ROM extensions to `VALID_ROM_EXTENSIONS` in `backend/app/core/config.py`:
   ```python
   "gba": {".gba"},
   ```
4. Place ROMs under `emulator/roms/gba/` and run **Scan library** in the UI.

No code changes to the backend logic are needed — `POST /play` resolves the core from `cores.json` at runtime.

---

## Known Limitations

| Limitation | Status |
|---|---|
| **Single user / one game at a time** | By design for home use. No multi-session support. |
| **x86_64 only (Docker)** | The Docker image downloads a `linux_amd64` MediaMTX binary and is validated on x86_64. ARM64 / Mac M-series not supported (build fails early with a clear message). |
| **PS2 (PCSX2) not supported yet** | `video_driver=null` is insufficient for PS2 — it requires real OpenGL/Vulkan (Xvfb or EGL headless). Planned. |
| **Safari / iOS not tested** | Tested on Chrome/Firefox (Android + desktop). WebRTC WHEP support in Safari is not validated. |
| **VAAPI/QSV not tested on real hardware** | Implemented and auto-detected; fallback to `libx264` is guaranteed. Not validated on a real Intel/AMD machine. |
| **No authentication** | All API routes and WebSocket are open. Use only on a trusted LAN. |
| **`--privileged` required for CIFS** | The Docker container requires `--privileged` to run `mount -t cifs`. If you don't use network storage, this could be reduced to `--cap-add SYS_ADMIN` (not yet implemented). |
| **Gamepad button mapping assumes Xbox-style** | `GAMEPAD_BUTTON_TO_KEY` in `frontend/app.js` maps physical button 0 → RetroPad B (Xbox convention). If buttons appear swapped with your controller, swap `"a"` and `"b"` in that map. |

---

## Security Considerations

RetroHost is a **home project** designed to run on a **trusted local network**. It deliberately prioritizes simplicity over hardened security. Please read [SECURITY.md](SECURITY.md) in full before use.

**TL;DR:**

- **Never expose to the internet.** No authentication exists on any route.
- **Never deploy on a public cloud server** (AWS, GCP, VPS, etc.).
- If you need remote access from outside your home, use a **VPN** to reach your LAN.
- The Docker container runs with `--privileged` — do not run untrusted images with this flag.
- RetroHost does **not** provide BIOS or ROM files. You must supply your own legally obtained copies.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for environment setup, coding conventions, and how to add support for new consoles.

Bug reports and pull requests are welcome. Please open an issue before submitting large changes so we can discuss the approach first.

---

## Credits

RetroHost is glue code: Python orchestration over a set of excellent open source projects that do the real work.

| Project | Role |
|---|---|
| [RetroArch](https://www.retroarch.com/) / [libretro](https://www.libretro.com/) | Headless emulation frontend |
| [PCSX-ReARMed](https://github.com/libretro/pcsx_rearmed) | PS1 libretro core (compiled from source) |
| [FFmpeg](https://ffmpeg.org/) | Video/audio encoding pipeline |
| [MediaMTX](https://github.com/bluenviron/mediamtx) | RTSP→WebRTC/WHEP server |
| [FastAPI](https://fastapi.tiangolo.com/) | REST API + WebSocket backend |
| [python-evdev](https://github.com/gvalkov/python-evdev) | Virtual input device (uinput) |

---

## License

[MIT](LICENSE) — free to use, modify, and redistribute, including commercially, provided the copyright notice is retained.

Note: RetroArch and most libretro cores are GPL-licensed. RetroHost invokes them as external processes (`subprocess`) and does not link against them — the MIT license applies to RetroHost's own code only.
