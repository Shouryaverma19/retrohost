# HomeGames — Arquitetura e Guia de Replicação

Este documento descreve a infraestrutura completa do HomeGames e como reproduzir o experimento do zero num Raspberry Pi 3. Para referência de uso/desenvolvimento do dia a dia, ver [README.md](README.md).

## O que é (e o que não é)

HomeGames transforma um Raspberry Pi 3 num servidor de **streaming de jogos retrô** — não em emulação no navegador.

**Importante**: não usamos o RetroArch WebPlayer (a build oficial Emscripten/WASM que roda o emulador inteiro dentro do navegador, sem servidor). A diferença é fundamental:

| | RetroArch WebPlayer (não usamos) | HomeGames (esta arquitetura) |
|---|---|---|
| Onde o emulador roda | No navegador, via WASM | No Raspberry Pi, binário nativo ARM |
| O que o navegador recebe | ROM + core `.wasm`, executa tudo localmente | Vídeo/áudio comprimido (H.264 + Opus) via WebRTC |
| Exigência do cliente | Navegador precisa rodar WASM pesado | Qualquer navegador moderno decodifica vídeo |
| Controle | JS lê teclado e injeta direto no emulador em memória | Navegador captura input e manda por WebSocket pro Pi, que injeta via `uinput` |

É o mesmo princípio do Steam Link/Moonlight/Stadia: captura, codifica, transmite, decodifica e exibe — o trabalho pesado (emulação) fica no Pi, o cliente só decodifica vídeo.

## Diagrama do pipeline completo

```
┌─────────────────────────────── Raspberry Pi 3 ───────────────────────────────┐
│                                                                                 │
│  RetroArch (headless)                                                          │
│  video_driver=null, input_driver=udev, audio_driver=alsa                       │
│  grava vídeo raw + áudio PCM ──┐                                               │
│                                  ▼                                             │
│                          /tmp/homegames_av.fifo (named pipe, container MKV)    │
│                                  │                                             │
│                                  ▼                                             │
│  ffmpeg (processo externo)                                                     │
│  lê o FIFO, codifica: h264_v4l2m2m (hw, /dev/video11) + libopus                 │
│  publica RTSP ──────────────────┐                                              │
│                                  ▼                                             │
│  mediamtx (servidor WebRTC/WHEP, processo sempre ativo)                        │
│  recebe RTSP, expõe via WHEP ───┐                                              │
│                                  │                                             │
│  ┌── teclado virtual uinput ◄────┼──── WebSocket /ws/input ◄────────┐          │
│  │   (lido pelo RetroArch        │                                  │          │
│  │    via input_driver=udev)     │                                  │          │
│  └────────────────────────────────                                  │          │
│                                  │                                  │          │
│  FastAPI (homegames.service, porta 8000)                            │          │
│  orquestra tudo acima via subprocess.Popen + injeta input            │          │
│                                  │                                  │          │
└──────────────────────────────────┼──────────────────────────────────┼──────────┘
                                   │ HTTP (REST) + WHEP (vídeo/áudio)  │ WebSocket (input)
                                   ▼                                  │
                          ┌─────────────────────────────────────────┴────┐
                          │              Navegador (cliente)               │
                          │  <video> recebe stream WebRTC (RTCPeerConnection)│
                          │  captura teclado/Gamepad API, manda por WS      │
                          └──────────────────────────────────────────────────┘
```

## Componentes e por que cada um existe

### 1. RetroArch (emulador, headless)

- **Binário**: `retroarch` via apt (`1.20.0+dfsg-2+b1` no Raspbian Trixie testado).
- **Cores libretro**: também via apt quando disponível (ex: SNES → `libretro-bsnes-mercury-performance`). Para PS1, não havia pacote no Trixie — compilado do source (`pcsx_rearmed_libretro.so`, `Makefile.libretro platform=armv7`, sem precisar do frontend standalone completo).
- **Por que headless**: o Pi não tem TV/monitor conectado. `video_driver = "null"` evita precisar de display físico ou GPU/shader compatível (o fallback gráfico padrão falhava por incompatibilidade GLSL/GLES no VC4).
- **Por que `input_driver = "udev"`**: não depende de sessão X11/Wayland (o driver `"x"` exige uma).
- **Por que `audio_driver = "alsa"`**: sem PulseAudio rodando neste setup; sem áudio real funcionando, o `audio_sync` do RetroArch não tem como limitar o ritmo do core, e o jogo roda em "fast forward" (~4x) — bug real observado e corrigido.
- **Captura de vídeo/áudio**: em vez do record nativo do RetroArch escrever direto num arquivo, ele escreve num **named pipe (FIFO)**, configurado via `--recordconfig config/retroarch/record_raw_av.cfg`:
  ```
  vcodec = "rawvideo"
  acodec = "pcm_s16le"
  format = "matroska"
  audio_enable = "true"
  pix_fmt = "yuv420p"
  ```
  Container Matroska (não `yuv4mpegpipe`) porque MKV é streamable via pipe (EBML não depende de seek para finalizar) e suporta áudio; `yuv4mpegpipe` é vídeo-only.
- **Por que não codificar direto no RetroArch**: o encoder de hardware do Pi (`h264_v4l2m2m`, driver `bcm2835-codec`) falha dentro do RetroArch com `Failed to set timeperframe` — esse driver não implementa o ioctl `VIDIOC_S_PARM`/`G_PARM` que o RetroArch tenta usar. Por isso o RetroArch só grava raw, e o encode de hardware acontece num processo externo (ffmpeg).

### 2. ffmpeg (encode)

- **Binário**: `ffmpeg` via apt (`7.1.5` no Trixie testado).
- Lê o FIFO, codifica vídeo via **hardware** (`-c:v h264_v4l2m2m`, usa `/dev/video11`, módulo kernel `bcm2835-codec`) e áudio via **Opus** (`-c:a libopus`) — não AAC, porque o mediamtx descarta silenciosamente trilhas AAC ao publicar via WHEP (navegadores não suportam AAC nativo em WebRTC, só Opus/G.711).
- Publica via RTSP para o mediamtx: `-f rtsp rtsp://127.0.0.1:8554/live`.
- Tuning de performance (validado no hardware real): `-g 15` (GOP curto, recupera de perda de pacote mais rápido que o padrão 30) e `-pkt_size 1200` (evita que o mediamtx precise remontar pacotes RTP maiores que o MTU da rede — 1460 > 1440 observado nos logs). Isso reduziu o jitter buffer de ~200ms para ~100ms e eliminou freezes visuais.
- Implementado em código: `backend/app/streaming/ffmpeg_webrtc.py` (`FFmpegStreamingProvider`).

### 3. mediamtx (servidor WebRTC/WHEP)

- **Binário**: não distribuído via apt — baixado do GitHub releases (`scripts/install_mediamtx.sh`, versão `v1.19.2`, asset `mediamtx_v1.19.2_linux_armv7.tar.gz`) para `bin/mediamtx` (não versionado no git).
- Recebe o stream RTSP do ffmpeg e expõe via **WHEP** (`POST` de SDP offer, recebe SDP answer) — o navegador usa `RTCPeerConnection` nativo, sem biblioteca JS externa.
- Roda como processo de infraestrutura **sempre ativo** (`mediamtx.service`), independente de haver jogo rodando ou não — diferente do RetroArch/ffmpeg, que só existem durante uma sessão de jogo.
- A API de controle do mediamtx (`api: true` em `config/mediamtx.yml`, porta `9997`) é usada pelo backend para confirmar que o stream está de fato publicado antes de liberar o frontend pra conectar via WHEP (ver `PlayerService._wait_stream_ready()`) — sem isso, há uma race condition real: o navegador conecta via WHEP antes do ffmpeg terminar de publicar, e a tela fica preta.

### 4. uinput (input remoto)

- O navegador captura **teclado do PC** (`keydown`/`keyup`) ou **gamepad físico** (`navigator.getGamepads()`, via polling em `requestAnimationFrame`) e manda só os eventos de mudança de estado (`{"key": "right", "pressed": true}`) por WebSocket (`/ws/input`).
- O backend usa **`python3-evdev`** (não `python-uinput`, que está abandonado) para criar um **teclado virtual** via `/dev/uinput` — o RetroArch lê isso exatamente como leria um teclado USB físico, porque já está configurado com `input_driver = "udev"`.
- Decisão de design: teclado virtual, não joystick/gamepad virtual — mais simples, porque o RetroArch já tem binds de teclado padrão para o RetroPad (`input_player1_a = "x"`, `input_player1_up = "up"`, etc.).
- `evdev` vem do **apt**, não pip — compilar a C extension no Pi 3 teria o mesmo custo de build que motivou abandonar `uvicorn[standard]`/uvloop. A venv do backend roda com `--system-site-packages` para acessá-lo.
- `/dev/uinput` por padrão é `root`-only; uma regra udev (`config/udev/99-uinput.rules`) libera para o grupo `input`.
- Implementado em código: `backend/app/input/` (`base.py`, `keymap.py`, `uinput_keyboard.py`), `backend/app/api/ws_input.py`.

### 5. Storage de ROMs (local ou rede)

- Por padrão, ROMs ficam em `emulator/roms/` no disco do próprio Pi.
- A interface web permite trocar para um share **CIFS/Samba** (ex: pendrive compartilhado por um roteador OpenWrt) sem editar nada via SSH — o backend monta via `sudo mount -t cifs` num ponto fixo (`/mnt/homegames-roms`).
- Privilégio elevado restrito por uma regra `sudoers` de escopo mínimo (`config/sudoers/homegames-mount`) — só o comando exato de mount/umount do destino fixo, sem sudo livre dentro do processo do serviço.
- Credenciais Samba vão para `/etc/samba/homegames-credentials` (`chmod 600`), nunca em texto plano no `config/storage.json` exposto via `GET /config`.
- `RetroArchDriver`/`PlayerService` não sabem nem precisam saber qual modo está ativo — recebem `game.launch_file`, um path de arquivo comum. `app/services/storage.py::effective_roms_dir()` decide o que o scanner varre.
- Trocar de storage **limpa o catálogo SQLite e força um re-scan** — `launch_file`/`path` são absolutos e únicos no banco; se a raiz mudar, entradas antigas ficam órfãs. Migrar para paths relativos seria over-engineering para o escopo doméstico/single-user deste projeto.
- Implementado em código: `backend/app/services/storage.py`, rotas `/storage`, `/storage/local`, `/storage/cifs` em `backend/app/api/routes.py`.

### 6. FastAPI (orquestração)

- **Binário/runtime**: `uvicorn` puro (sem `[standard]` — essa escolha deliberada evita compilar `uvloop` no Pi 3, risco de OOM/lentidão).
- Nunca fala diretamente com RetroArch, ffmpeg ou uinput — tudo passa por interfaces (`EmulatorDriver`, `StreamingProvider`, `InputProvider`) implementadas concretamente e injetadas no `PlayerService` (`backend/app/services/player.py`), que orquestra a sequência de start/stop.
- WebSocket precisa de um backend ASGI de WS — `wsproto` (pure Python, sem tempo de build) em vez de `websockets` (sem wheel ARMv7, compilaria do source).
- Roda como `homegames.service`, dependente de `mediamtx.service` já estar de pé (`After=`/`Wants=`).
- Frontend: HTML/CSS/JS puro (`frontend/`), sem build step, servido como arquivos estáticos pelo próprio FastAPI.

### Sequência de uma sessão de jogo (`POST /play` → `POST /stop`)

1. `RetroArchDriver.launch()`: cria o FIFO, lança RetroArch headless com `--recordconfig`.
2. `UInputKeyboardProvider.connect()`: cria o teclado virtual via `evdev.UInput`.
3. Pausa curta (tempo do RetroArch abrir o FIFO).
4. `FFmpegStreamingProvider.start()`: lança ffmpeg lendo o FIFO, publicando RTSP.
5. `PlayerService._wait_stream_ready()`: faz polling na API do mediamtx até confirmar o stream publicado (timeout 10s) — só então a requisição HTTP retorna 200.
6. Frontend conecta via WHEP (vídeo/áudio) e abre o WebSocket de input.
7. `POST /stop`: ordem inversa — desconecta input, para o ffmpeg, para o RetroArch, remove o FIFO.

## Guia de replicação do zero

### Hardware/SO necessário

- Raspberry Pi 3 (testado; provavelmente funciona em qualquer Pi com encoder de hardware V4L2, mas não validado).
- Raspberry Pi OS Lite, Debian Trixie (testado: kernel `6.18.34+rpt-rpi-v7`). Não precisa de desktop/X11.
- Acesso SSH por chave pública configurado.
- Pelo menos uma ROM legalmente obtida e um core libretro compatível.

### Passo 1 — Sistema base e RetroArch

```bash
sudo apt-get update
sudo apt-get install -y retroarch retroarch-assets ffmpeg python3-venv git
# Cores libretro disponíveis via apt variam por console - exemplo SNES:
sudo apt-get install -y libretro-bsnes-mercury-performance
```

Se o core do seu console não tiver pacote apt (como aconteceu aqui com PS1/PCSX-ReARMed), vai precisar compilar do source — `Makefile.libretro platform=armv7` no repositório do core, sem precisar do frontend standalone completo (evita dependências de SDL1.2/ALSA dev).

### Passo 2 — Clonar e configurar o projeto

```bash
git clone <url-do-seu-fork> /home/vitor/homegames
cd /home/vitor/homegames/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Organize ROMs em `emulator/roms/<console>/<jogo>/`, BIOS em `emulator/bios/`, e mapeie os cores em `config/cores.json`:

```json
{
  "ps1": "/home/vitor/homegames/emulator/cores/pcsx_rearmed_libretro.so",
  "snes": "/home/vitor/homegames/emulator/cores/snes.so"
}
```

(pode ser um caminho direto ou um symlink para o `.so` instalado via apt, ex: `/usr/lib/arm-linux-gnueabihf/libretro/bsnes_mercury_performance_libretro.so`).

### Passo 3 — Configurar RetroArch para modo headless

```bash
# gera o retroarch.cfg padrão em ~/.config/retroarch/ se ainda não existir
retroarch --help > /dev/null 2>&1 || true
bash scripts/setup_streaming.sh
```

Esse script ajusta `video_driver=null`, `input_driver=udev`, `audio_driver=alsa` no `retroarch.cfg`, e algumas flags em `/boot/firmware/config.txt`.

### Passo 4 — Instalar e configurar o mediamtx

```bash
bash scripts/install_mediamtx.sh
sudo cp config/mediamtx.yml /home/vitor/homegames/config/mediamtx.yml  # já está no repo
sudo cp scripts/mediamtx.service /etc/systemd/system/mediamtx.service
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx
```

Confirme `api: true` em `config/mediamtx.yml` (necessário para o backend confirmar quando o stream está pronto).

### Passo 5 — Habilitar input remoto (uinput)

```bash
bash scripts/setup_input.sh
```

Esse script (idempotente): instala `python3-evdev` via apt, garante o módulo `uinput` carregado e persistente, instala a regra udev (`config/udev/99-uinput.rules`) liberando `/dev/uinput` para o grupo `input`, e recria a venv do backend com `--system-site-packages`.

### Passo 6 — Subir o serviço da API

```bash
sudo cp scripts/homegames.service /etc/systemd/system/homegames.service
sudo systemctl daemon-reload
sudo systemctl enable --now homegames
sudo systemctl status mediamtx homegames
```

### Passo 7 — Validar

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/scan
curl http://localhost:8000/games
```

Abra `http://<ip-do-pi>:8000` no navegador, clique "Jogar" num jogo da lista. Deve aparecer vídeo+áudio via WebRTC em poucos segundos, e teclado do PC (setas, Enter, Z/X/A/S/Q/W) ou um gamepad físico já controlam o jogo.

### Passo opcional — storage de ROMs via rede (CIFS/Samba)

```bash
bash scripts/setup_network_storage.sh
```

Instala `cifs-utils`, cria `/mnt/homegames-roms` e a regra sudoers de mount com escopo mínimo. Depois disso, use o botão "Configurar storage" na interface web para apontar para um share CIFS (host, nome do share, usuário, senha, subpasta opcional) — sem precisar editar config nem reiniciar o serviço manualmente.

Se o servidor Samba for outro OpenWrt: `invalid users = root` no `smb.conf` é comum por padrão (boa prática de segurança) — não tente autenticar como `root`, crie um usuário Unix não-root (`useradd`) e dê a ele uma senha Samba própria (`smbpasswd -a <usuario>`). Confirme com `pdbedit -L` no roteador que o usuário realmente foi cadastrado antes de assumir que a senha está errada.

### Pontos de atenção ao replicar

- **`core_path` precisa existir antes de tentar jogar** — `POST /play` retorna HTTP 409 com mensagem clara se o core configurado em `config/cores.json` não existir no disco, em vez de falhar silenciosamente.
- **`.gitattributes`** força LF em `*.sh`/`*.service`/`*.rules` — importante se você desenvolve em Windows como neste projeto; sem isso, `git archive`/checkout com `core.autocrlf=true` quebra scripts shell no Pi (`set -o pipefail` falha com "invalid option name" por causa do `\r` residual).
- **mediamtx precisa estar de pé antes do homegames** — a dependência `After=`/`Wants=` no `homegames.service` cobre isso no boot, mas em testes manuais lembre de checar `systemctl status mediamtx` primeiro.
- **Mapeamento de gamepad físico** (`GAMEPAD_BUTTON_TO_KEY` em `frontend/app.js` e `backend/app/input/keymap.py`) assume convenção Xbox-style (botão físico "A" → RetroPad B). Validado só com teclado até agora — se os botões saírem trocados com um controle físico real, é uma linha pra inverter, sem mudança de arquitetura.

## Modo container (agnóstico de GPU/SO)

A branch `docker_linux` empacota todo o pipeline num **container Docker único e agnóstico** — a MESMA imagem roda em qualquer máquina (Windows/WSL2 ou Linux nativo; NVIDIA, Intel, AMD ou só CPU). A motivação inicial foi latência: a investigação (ver abaixo) mostrou que os ~376ms residuais são **teto do Pi 3** (o encoder `h264_v4l2m2m` satura, ffmpeg preso em ~1.06x). Em x86 com encode por GPU o gargalo some (medido: jitter buffer de vídeo caiu de ~145ms no Pi para **~93ms** com NVENC numa RTX 4050).

**Encoder auto-detectado:** no boot, o container roda um *encode-probe* real de cada candidato na ordem `h264_nvenc` (NVIDIA) → `h264_qsv` (Intel QuickSync) → `h264_vaapi` (AMD/Intel) → `libx264` (CPU), e usa o primeiro que funciona. Sem GPU, cai para software e sobe igual. O probe testa o caminho completo (lib + driver + device), não só "o encoder está compilado". Ver `backend/app/streaming/encoder_detect.py` e `encoder_profiles.py`. A flag de GPU no `docker run` é opcional: `--gpus all` (NVIDIA), `--device /dev/dri` (Intel/AMD), ou nenhuma (CPU).

**O que muda em relação ao Pi:**

| | Raspberry Pi 3 | Container (agnóstico) |
|---|---|---|
| Encoder de vídeo | `h264_v4l2m2m` (hardware Pi) | auto: nvenc / qsv / vaapi / libx264 |
| Imagem base | — (apt no SO) | `ubuntu:24.04` (~2GB; era 5.7GB com base CUDA) |
| Input | uinput/udev | SDL2 virtual joystick via LD_PRELOAD (não depende de udev) |
| Orquestração de processos | 2 systemd units | `scripts/docker-entrypoint.sh` (supervisor bash) |
| Render headless | `video_driver=null` | `video_driver=null` (igual; PS2 exigirá GL/Vulkan real) |

**O que NÃO muda:** todo o backend (`drivers/`, `services/`, `api/`), o frontend e o pipeline conceitual (RetroArch → FIFO → ffmpeg → mediamtx → WebRTC). A arquitetura já era desacoplada — o driver lê `retroarch` do PATH e os paths derivam de `HOMEGAMES_ROOT`. As mudanças de código são pontuais e retrocompatíveis com o Pi via env/defaults: encoder selecionável/auto-detectado (`HOMEGAMES_ENCODER`), provider de input selecionável (`HOMEGAMES_INPUT_PROVIDER=sdl|uinput`).

**Arquivos:** `Dockerfile`, `.dockerignore`, `scripts/docker-entrypoint.sh` (gera `retroarch.cfg` headless + `cores.json`, sobe PulseAudio null-sink + mediamtx + uvicorn, detecta encoder), `container/sdl_input_preload.c` (LD_PRELOAD do input SDL), `docker-run-windows.sh`/`docker-run.sh` (helpers).

**Soluções de container já implementadas e validadas (Docker Desktop/WSL2 + RTX 4050):**

- **Áudio**: PulseAudio null-sink interno como clock (sem `/dev/snd`), evita o *fast forward*.
- **Input**: SDL2 virtual joystick via LD_PRELOAD dentro do RetroArch — uinput/udev não funciona no WSL2 (sem udevd o libudev não enumera devices). Funciona no PC e celular.
- **Encoder**: auto-detectado (nvenc/qsv/vaapi/libx264); imagem agnóstica de GPU.
- **Storage CIFS**: persiste em `/data` (volume) e remonta no boot e on-demand.

**Pendências:**

1. **VAAPI/QSV** (Intel/AMD): implementados, **não testados nesse hardware** (a máquina de validação é NVIDIA). O fallback para `libx264` garante que sobe de qualquer forma.
2. **PS2 (PCSX2)** — `cores.json` mapeia console→core, mas **não validado**: `video_driver=null` provavelmente não basta (PS2 precisa de GL/Vulkan → Xvfb/EGL). Próximo objetivo.
3. Confirmar **Safari/iOS** (testado Android) e que o áudio chega junto do vídeo.

## Pendências conhecidas (estado atual do experimento)

- Delay de input remoto: **investigado e reduzido de 1.25s para ~376ms** (remoção do `-re` do ffmpeg + `-fps_mode passthrough`); o residual é teto de hardware do Pi 3 (ver "Modo container" para o caminho de melhoria via NVENC/x86).
- Gamepad físico (Gamepad API) ainda não testado com hardware real, só teclado do PC.
- Sem autenticação em nenhuma rota (aceitável para uso doméstico em LAN, não exponha a internet sem adicionar isso).
- Suporta apenas um jogo por vez (estado em memória no `PlayerService`, sem fila/multi-sessão).
- PS2 (PCSX2) não suportado ainda — alvo da versão containerizada em hardware x86.
