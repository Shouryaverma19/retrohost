# HomeGames

HomeGames transforma um Raspberry Pi em um servidor local de jogos retrô acessível por navegador. Sem cliente para instalar: aponte o navegador para o IP do Raspberry e jogue.

Jogos rodam via streaming (WebRTC) — sem precisar de TV/teclado/controle conectados ao Pi. Core PS1 (PCSX-ReARMed) compilado e funcionando, pipeline de streaming validado e formalizado em código (ver [Streaming para o navegador](#streaming-para-o-navegador)), e input remoto (teclado do navegador ou gamepad físico) já implementado (ver [Input remoto](#input-remoto-teclado-e-gamepad)).

Para o desenho completo da infraestrutura (diagrama do pipeline, por que cada componente existe) e um guia passo a passo para replicar o experimento do zero, ver [ARCHITECTURE.md](ARCHITECTURE.md).

> ⚠️ **Uso doméstico em LAN.** Não há autenticação e o container roda com privilégio elevado. **Não exponha à internet nem suba em cloud pública.** O projeto **não fornece BIOS nem ROMs** — use as suas, obtidas legalmente. Leia [SECURITY.md](SECURITY.md) antes de usar.

## Filosofia

- Sem RetroPie — Raspberry Pi OS Lite puro.
- Arquitetura modular: a API nunca fala diretamente com RetroArch. Toda execução de emulador passa por uma interface `EmulatorDriver`, então o backend de emulação pode ser substituído sem tocar na API.
- Simplicidade antes de abstração prematura.

## Créditos

HomeGames é só a cola: orquestração em Python sobre um conjunto de projetos open source que fazem o trabalho pesado de emulação, codificação e transporte. Sem eles, nada disto existiria.

| Projeto | Licença | Papel no HomeGames |
| --- | --- | --- |
| [RetroArch](https://www.retroarch.com/) / [libretro](https://www.libretro.com/) | GPLv3 (RetroArch); cores variam por projeto | Frontend de emulação. Roda headless no Pi (`video_driver=null`) e grava vídeo/áudio raw num named pipe — ver [drivers/retroarch.py](backend/app/drivers/retroarch.py). |
| [PCSX-ReARMed](https://github.com/libretro/pcsx_rearmed) | GPLv2 | Core libretro de PS1 usado nos testes (compilado do source para ARMv7, sem pacote apt disponível no Trixie). |
| [bsnes-mercury](https://github.com/libretro/bsnes-mercury) | GPLv3 | Core libretro de SNES (instalado via apt, `libretro-bsnes-mercury-performance`). |
| [FFmpeg](https://ffmpeg.org/) | LGPL/GPL (depende dos componentes habilitados) | Lê o FIFO do RetroArch e codifica vídeo via encoder de hardware (`h264_v4l2m2m`) + áudio Opus, publicando RTSP — ver [streaming/ffmpeg_webrtc.py](backend/app/streaming/ffmpeg_webrtc.py). |
| [MediaMTX](https://github.com/bluenviron/mediamtx) | MIT | Servidor que recebe o RTSP do ffmpeg e expõe o stream ao navegador via WHEP/WebRTC. |
| [FastAPI](https://fastapi.tiangolo.com/) | MIT | Framework da API REST + WebSocket que orquestra todo o backend. |
| [Uvicorn](https://www.uvicorn.org/) | BSD-3-Clause | Servidor ASGI que roda a aplicação FastAPI. |
| [Starlette](https://www.starlette.io/) | BSD-3-Clause | Toolkit ASGI sobre o qual o FastAPI é construído (dependência transitiva). |
| [Pydantic](https://docs.pydantic.dev/) | MIT | Validação de schemas (requests/responses da API). |
| [SQLAlchemy](https://www.sqlalchemy.org/) | MIT | ORM usado para o catálogo de jogos em SQLite. |
| [wsproto](https://github.com/python-hyper/wsproto) | MIT | Implementação WebSocket usada pelo Uvicorn (`/ws/input`) — escolhida por ser pure Python, sem custo de compilação no Pi 3. |
| [python-evdev](https://github.com/gvalkov/python-evdev) | BSD-3-Clause | Cria o teclado virtual via Linux `uinput`, usado para injetar input remoto no RetroArch — ver [input/uinput_keyboard.py](backend/app/input/uinput_keyboard.py). |
| [Raspberry Pi OS](https://www.raspberrypi.com/software/) (Debian) | GPL (base Debian) | Sistema operacional do Pi. |
| Gamepad API / Fullscreen API / WebRTC (`RTCPeerConnection`) | Padrões web (W3C/WHATWG) | APIs nativas do navegador usadas no frontend — nenhuma biblioteca JS externa foi necessária. |

O código do HomeGames em si é licenciado sob [MIT](LICENSE) — ver [Licença](#licença). Note que algumas dependências acima (RetroArch e a maioria dos cores libretro) são GPL; isso afeta como você pode distribuir um binário que as empacote junto, mas não restringe o código do HomeGames, que apenas as invoca como processos externos via `subprocess`.

## Árvore do projeto

```
home_game/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # cria o FastAPI app, monta frontend e API
│       ├── api/routes.py      # todos os endpoints REST
│       ├── core/config.py     # caminhos e configuração central
│       ├── db/                # engine SQLAlchemy + sessão
│       ├── models/game.py     # tabela `games`
│       ├── schemas/game.py    # schemas Pydantic
│       ├── services/
│       │   ├── scanner.py     # varre o storage de ROMs ativo e popula o SQLite
│       │   ├── storage.py     # local vs CIFS/Samba - monta/desmonta, decide ROMS_DIR efetivo
│       │   └── player.py      # orquestra play/stop/status sobre o driver
│       ├── drivers/
│       │   ├── base.py        # interface EmulatorDriver
│       │   └── retroarch.py   # RetroArch headless gravando p/ FIFO
│       ├── streaming/
│       │   ├── base.py            # interface StreamingProvider
│       │   └── ffmpeg_webrtc.py   # ffmpeg lendo o FIFO, encode hw, publica RTSP
│       ├── input/
│       │   ├── base.py            # interface InputProvider (connect/disconnect/press/release/release_all)
│       │   ├── keymap.py          # mapa botao Gamepad API / tecla logica -> keycode evdev
│       │   └── uinput_keyboard.py # UInputKeyboardProvider: teclado virtual via Linux uinput
│       └── api/ws_input.py    # rota WebSocket /ws/input (fora de api/routes.py, transporte diferente)
├── frontend/                  # HTML/CSS/JS puro, sem build step — player WHEP + lista de jogos + input
├── emulator/
│   ├── bios/
│   ├── cores/                 # arquivos .so dos cores libretro
│   ├── roms/ps1/              # ROMs organizadas por console/pasta de jogo
│   ├── saves/
│   └── states/
├── config/
│   ├── cores.json             # mapa console -> caminho do core .so
│   ├── settings.json
│   ├── storage.json           # modo de storage ativo (local/cifs), gravado pela API
│   ├── mediamtx.yml           # config do servidor WebRTC/WHEP (streaming)
│   ├── udev/
│   │   └── 99-uinput.rules    # regra udev: libera /dev/uinput pro grupo "input"
│   ├── sudoers/
│   │   └── homegames-mount    # regra sudoers: mount/umount cifs com escopo minimo
│   └── retroarch/
│       └── record_raw_av.cfg  # recordconfig: RetroArch grava raw video+audio p/ FIFO
├── logs/
├── bin/                        # binários de terceiros baixados (não versionado, ver install_mediamtx.sh)
└── scripts/
    ├── deploy.sh                # rsync local -> Raspberry Pi
    ├── homegames.service         # unit systemd (API + frontend)
    ├── mediamtx.service          # unit systemd (servidor WebRTC/WHEP)
    ├── install_mediamtx.sh       # baixa o binário mediamtx (ARMv7)
    ├── setup_streaming.sh        # configura RetroArch headless no Pi (idempotente)
    ├── setup_input.sh            # configura uinput/udev + recria venv com --system-site-packages (idempotente)
    ├── setup_network_storage.sh  # instala cifs-utils + regra sudoers de mount (idempotente)
    ├── stream_pipeline.sh        # orquestra RetroArch + ffmpeg manualmente (debug)
    └── whep_test.html            # página standalone p/ testar o player WHEP (debug)
```

## Requisitos técnicos

- Python 3.11+
- FastAPI, Uvicorn, Pydantic, SQLAlchemy
- RetroArch instalado no sistema (via apt) com pelo menos um core libretro
- SQLite (sem servidor externo necessário)

## Modo container (agnóstico de GPU)

Além do Raspberry Pi, há uma versão containerizada (branch `docker_linux`) que roda em qualquer PC **x86_64** — Windows (Docker Desktop/WSL2) ou Linux nativo; NVIDIA, Intel, AMD ou só CPU. A imagem é única e o encoder de vídeo é **auto-detectado** no boot (`nvenc > qsv > vaapi > libx264`), caindo para software se não houver GPU. Ver [ARCHITECTURE.md](ARCHITECTURE.md) (seção "Modo container").

**Pré-requisitos do host** (o Docker não instala isto por você):

- **Docker** (Desktop no Windows, ou Engine no Linux). Arquitetura **x86_64** — ARM/Mac M1+ não é suportado (o build falha com mensagem clara).
- Para **NVIDIA**: o [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) instalado no host (necessário para `--gpus all`).
- Para **Intel/AMD**: `/dev/dri` disponível no host (drivers da GPU instalados no SO).
- Sem GPU / nada disso: funciona mesmo assim, em CPU (libx264).

**Build:**
```bash
docker build -t homegames .
```

**Run** — a flag de GPU é **opcional** (sem ela, roda em CPU via libx264):
```bash
# NVIDIA (NVENC) — requer nvidia-container-toolkit no host
docker run -d --name homegames --privileged --gpus all \
  -p 8000:8000 -p 8889:8889 -p 8554:8554 -p 8189:8189/udp \
  -v homegames-data:/data homegames

# Intel/AMD (QuickSync/VAAPI) — troque --gpus all por:
#   --device /dev/dri

# Sem GPU (CPU/libx264) — omita ambas as flags. Sobe em qualquer máquina.
```

No Windows há o helper `docker-run-windows.sh` (controla a GPU por `HOMEGAMES_GPU=nvidia|dri|none`). A UI fica em `http://<host>:8000` — use o IP da LAN (não `localhost`) para acessar de outros dispositivos.

O encoder pode ser forçado com `HOMEGAMES_ENCODER` (`h264_nvenc`, `h264_qsv`, `h264_vaapi`, `libx264`) como override da auto-detecção. O log do boot mostra qual encoder foi escolhido.

## Setup no Raspberry Pi

```bash
cd /home/vitor/homegames/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Rodando manualmente

```bash
cd /home/vitor/homegames/backend
source .venv/bin/activate
export HOMEGAMES_ROOT=/home/vitor/homegames
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

A variável `HOMEGAMES_ROOT` é opcional no Raspberry (o padrão já assume `/home/vitor/homegames` a partir da posição do código), mas é necessária para rodar em outra máquina/ambiente de desenvolvimento (ex: Windows), apontando para a raiz local do projeto.

## Testando com curl

```bash
# Healthcheck
curl http://localhost:8000/health

# Escanear a biblioteca de ROMs
curl -X POST http://localhost:8000/scan

# Listar jogos encontrados
curl http://localhost:8000/games

# Ver configuração de cores/diretórios
curl http://localhost:8000/config

# Tentar jogar (game_id obtido de /games; requer mediamtx rodando, ver "Streaming para o navegador")
curl -X POST http://localhost:8000/play \
  -H "Content-Type: application/json" \
  -d '{"game_id": 1}'

# Ver status atual
curl http://localhost:8000/status

# Parar o jogo em execução
curl -X POST http://localhost:8000/stop
```

## Acessando pelo navegador

Com o servidor rodando no Raspberry Pi:

```
http://homegames.local:8000
```

ou, usando o IP fixo configurado:

```
http://<IP_DO_RASPBERRY>:8000
```

A página mostra a lista de jogos com botão "Jogar" por jogo. Ao clicar, a tela troca para o player de vídeo (stream WebRTC, sem controles nativos de pause/seek — pausar a UI não pausaria o jogo no Pi) com os botões "Tela cheia" e "Encerrar jogo". Saltar fora do fullscreen (ESC) não encerra o jogo — é preciso clicar em "Encerrar jogo" explicitamente, que aparece normalmente fora do modo fullscreen. Se o jogo for deixado rodando em segundo plano (ex: recarregar a página sem clicar "Encerrar jogo"), a tela ociosa mostra um aviso com o título do jogo e um botão para encerrá-lo.

## Deploy do código local para o Raspberry Pi

Este projeto é desenvolvido localmente (com git) e sincronizado para o Pi via rsync sobre SSH:

```bash
./scripts/deploy.sh <IP_DO_RASPBERRY>
# ou
HOMEGAMES_PI_HOST=<IP_DO_RASPBERRY> ./scripts/deploy.sh
```

O script usa o usuário `vitor` (não `root`) e ignora `.git/`, `.venv/`, `__pycache__/`, `*.db` e o arquivo de credenciais.

## Criando os serviços systemd (start automático)

O HomeGames depende de dois serviços: `mediamtx` (servidor WebRTC/WHEP de streaming, sempre ativo) e `homegames` (API + frontend, depende do mediamtx já estar de pé).

```bash
sudo cp /home/vitor/homegames/scripts/mediamtx.service /etc/systemd/system/mediamtx.service
sudo cp /home/vitor/homegames/scripts/homegames.service /etc/systemd/system/homegames.service
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx
sudo systemctl enable --now homegames
sudo systemctl status mediamtx homegames
```

Logs dos serviços:

```bash
journalctl -u homegames -f
journalctl -u mediamtx -f
```

Para habilitar input remoto (teclado/gamepad do navegador), antes de subir o `homegames.service` rode uma vez (idempotente):

```bash
bash /home/vitor/homegames/scripts/setup_input.sh
```

Isso instala `python3-evdev`, configura a regra udev de `/dev/uinput` e recria a venv do backend com `--system-site-packages` (ver [Input remoto](#input-remoto-teclado-e-gamepad)).

## Sobre o core de PS1

O Raspbian Trixie não tem pacote apt para `pcsx-rearmed`. **Já resolvido**: o core foi compilado a partir do source (`src/pcsx_rearmed/`, build via `Makefile.libretro platform=armv7`, sem precisar do `./configure` do frontend standalone — esse exige SDL1.2/ALSA dev e não é necessário para gerar só o core `.so`). O binário gerado (`pcsx_rearmed_libretro.so`) está em `emulator/cores/`, mapeado em `config/cores.json`, e o Dino Crisis já roda de ponta a ponta via `POST /play` (validado no HDMI real do Pi).

Se o core ainda não estiver presente num novo setup: `POST /play` retorna **HTTP 409** com mensagem explicando que o core não foi configurado, em vez de falhar silenciosamente ou travar o backend. Para adicionar um novo console/core: copie o `.so` para `emulator/cores/` e registre o caminho em `config/cores.json` — nenhuma alteração de código é necessária.

## Streaming para o navegador

`POST /play` agora sempre inicia o jogo em modo streaming — não há mais saída local via HDMI. O jogo é capturado, codificado em H.264 por hardware e entregue ao navegador via WebRTC (sem plugin, sem instalar nada no cliente).

**Pipeline validado manualmente no hardware real** (Raspberry Pi 3): RetroArch (headless, sem display físico) → grava vídeo raw + áudio PCM no mesmo named pipe (container Matroska) → `ffmpeg` lê o pipe e codifica vídeo via encoder de hardware (`h264_v4l2m2m`, usa `/dev/video11`) e áudio via Opus → publica RTSP para o `mediamtx` → navegador consome via WHEP (WebRTC, vídeo + áudio sincronizados) sem plugin nem biblioteca JS externa.

Descobertas importantes que guiam a implementação (detalhes técnicos completos no histórico do projeto):

- O record driver nativo do RetroArch (`-r arquivo.mkv`) usa codec de software por padrão e **não consegue usar o encoder de hardware** (`h264_v4l2m2m` falha dentro do RetroArch com `Failed to set timeperframe` — o driver `bcm2835-codec` não implementa o ioctl que o RetroArch tenta usar). Por isso o encode acontece num processo `ffmpeg` externo, lendo um FIFO onde o RetroArch grava apenas raw video + áudio PCM.
- RetroArch precisa rodar com `video_driver = "null"` (sem GL/DRM — o fallback gráfico falha por incompatibilidade de shader GLSL com o GLES do VC4/Mesa), `input_driver = "udev"` (não depende de X11) e `audio_driver = "alsa"` (sem áudio funcionando, `audio_sync` não consegue limitar o ritmo do core e o jogo roda em "fast forward").
- **Áudio precisa ser Opus, não AAC** — o mediamtx descarta silenciosamente trilhas AAC ao publicar via WHEP (`WAR [WebRTC] skipping track 2 (MPEG-4 Audio)`), porque navegadores não suportam AAC nativamente em WebRTC.
- Setup necessário no Pi: `scripts/setup_streaming.sh` (ajusta `retroarch.cfg` e `/boot/firmware/config.txt`, idempotente), `scripts/install_mediamtx.sh` (baixa o binário ARMv7, não há pacote apt), `scripts/stream_pipeline.sh` (orquestra RetroArch + ffmpeg manualmente para teste), `scripts/whep_test.html` (página standalone para testar o player no navegador sem depender do frontend real).

**Performance medida no hardware real** (`RTCPeerConnection.getStats()`): CPU com folga real (`retroarch` ~60-77% de 1 dos 4 cores, `ffmpeg` ~30%, `mediamtx` ~5%; load average ~1.5-1.7 de 4.0), RAM com ~680MB sempre livres de 920MB total. Latência (jitter buffer + processamento) ~100ms, sem freezes de vídeo, depois de reduzir o GOP do encoder (30→15 frames) e fixar `-pkt_size 1200` no ffmpeg (evitava remontagem de pacotes RTP no mediamtx). Conclusão: o Pi 3 sustenta esse pipeline com folga, sem precisar reduzir resolução/bitrate.

**Implementado em código** (`backend/app/streaming/ffmpeg_webrtc.py`, `backend/app/drivers/retroarch.py`, `backend/app/services/player.py`): `RetroArchDriver.launch()` sempre cria o FIFO e lança o RetroArch headless com `--recordconfig=config/retroarch/record_raw_av.cfg`; `PlayerService.play()` aguarda um curto intervalo (tempo do RetroArch abrir o FIFO, validado manualmente) e então inicia o `FFmpegStreamingProvider`, que lê o FIFO e publica no mediamtx, só retornando depois que a API do mediamtx confirma o stream publicado (`GET /v3/paths/get/live`, campo `ready`) — isso evita que o frontend conecte via WHEP antes de haver stream (bug observado: tela preta porque o navegador conectava antes do ffmpeg publicar). `GET /config` expõe `whep_url` para o frontend não precisar hardcodar o IP do Pi.

## Input remoto (teclado e gamepad)

Com vídeo/áudio funcionando via streaming, falta o jogador conseguir controlar o jogo — o Pi roda headless, sem teclado/controle físico conectado a ele. A solução: o navegador captura input local (teclado do PC ou gamepad físico via Gamepad API) e manda só os eventos de mudança de estado (`{"key": "right", "pressed": true}`) por WebSocket para o backend, que injeta isso no Pi como teclas de um **teclado virtual** via Linux `uinput` — o RetroArch lê isso exatamente como leria um teclado USB físico, porque já está configurado com `input_driver = "udev"`.

Decisão de design: teclado virtual (não joystick/gamepad virtual) porque o RetroArch já tem binds de teclado padrão para o RetroPad (`input_player1_a = "x"`, `input_player1_up = "up"`, etc, confirmados em `~/.config/retroarch/retroarch.cfg`) — não foi preciso configurar nada novo no RetroArch.

**Setup de sistema** (`scripts/setup_input.sh`, executado uma vez via SSH, idempotente):

- Instala `python3-evdev` via **apt**, não pip — compilar a C extension do `evdev` no Pi 3 teria o mesmo custo que motivou abandonar `uvicorn[standard]`/uvloop. `evdev` é o pacote ativamente mantido (o `python-uinput` do PyPI está abandonado e exigiria build from source).
- Garante o módulo `uinput` carregado e persistente (`/etc/modules-load.d/uinput.conf`).
- Instala `config/udev/99-uinput.rules` (`KERNEL=="uinput", GROUP="input", MODE="0660"`) e aplica com `udevadm trigger` — sem precisar de reboot.
- Recria a venv do backend com `--system-site-packages`, para conseguir importar o `evdev` instalado via apt.

A rota WebSocket nova (`/ws/input`) também exigiu um backend ASGI de WebSocket: `uvicorn` puro (sem `[standard]`) não inclui nenhum, e `websockets` não tem wheel ARMv7 (compilaria do source). Por isso `requirements.txt` usa `wsproto` — pure Python, sem tempo de build.

**Implementado em código**:

- `backend/app/input/base.py` — interface `InputProvider` (`connect`/`disconnect`/`press`/`release`/`release_all`).
- `backend/app/input/uinput_keyboard.py` — `UInputKeyboardProvider`, cria o teclado virtual via `evdev.UInput` e traduz `press`/`release` em eventos de tecla. `release_all()` solta todas as teclas atualmente pressionadas — usado como salvaguarda quando o WebSocket cai abruptamente (ex: fechar a aba com um botão segurado), para nenhuma tecla ficar "travada".
- `backend/app/input/keymap.py` — mapa nome lógico → keycode evdev, e índice de botão do Gamepad API → nome lógico.
- `backend/app/api/ws_input.py` — rota `/ws/input`, recebe `{"key": ..., "pressed": ...}` por mensagem e chama `PlayerService.handle_input()`.
- `PlayerService` conecta o input logo após `driver.launch()` (antes do streaming subir) e desconecta no `stop()` — simétrico ao padrão já usado para `EmulatorDriver`/`StreamingProvider`.
- `frontend/app.js` — captura `keydown`/`keyup` (setas, Enter, Z/X/A/S/Q/W) e faz polling de `navigator.getGamepads()` via `requestAnimationFrame` (só envia mensagem quando o estado de um botão muda, não a cada frame). Conecta/desconecta o WebSocket nos mesmos pontos onde a conexão WHEP já é aberta/fechada (`playGame()`/`stopGame()`).

**Validado no hardware real**: teclado do navegador (setas + Enter) controlando o RetroArch no Pi via streaming, confirmado pelo usuário. Bug corrigido durante o teste: apertar Enter pausava o vídeo (atalho nativo do elemento `<video>` para play/pause) — corrigido com `event.preventDefault()` em toda tecla mapeada, antes do navegador interpretar como atalho de mídia.

**Pendências conhecidas**:

- Delay perceptível entre apertar a tecla e a reação no jogo — relatado pelo usuário, ainda não medido/diagnosticado (candidatos a investigar: latência do próprio WebSocket, possível atraso introduzido pelo polling do Gamepad API via `requestAnimationFrame`, ou simplesmente a mesma latência de ~100ms já presente no pipeline de vídeo somada ao round-trip do input).
- Mapeamento de botões do Gamepad API (`GAMEPAD_BUTTON_TO_KEY` em `frontend/app.js` e `backend/app/input/keymap.py`) assume a convenção Xbox-style (botão físico "A" → RetroPad B) usada pelos autoconfigs do libretro, mas **ainda não testado com um gamepad físico real** — só teclado do navegador foi validado até agora. Fácil de inverter (uma linha no dict) se sair trocado no teste.

## Storage de ROMs via rede (CIFS/Samba)

Por padrão, ROMs ficam em `emulator/roms/` no próprio Pi. A interface web permite trocar isso para um share de rede (ex: um pendrive compartilhado por um roteador OpenWrt via Samba) sem precisar editar nada via SSH — botão **"Configurar storage"** na tela inicial.

**Como funciona**: o backend monta o share via `mount -t cifs` no sistema operacional do Pi, num ponto fixo (`/mnt/homegames-roms`), e o scanner passa a varrer esse diretório (ou uma subpasta dele, se configurada) em vez do disco local. `RetroArchDriver`/`PlayerService` não mudam nada — eles só recebem `game.launch_file`, um path de arquivo comum, sem saber se é disco local ou montagem de rede por baixo.

**Setup de sistema** (`scripts/setup_network_storage.sh`, executado uma vez via SSH, idempotente):

- Instala `cifs-utils` via apt.
- Cria o ponto de montagem `/mnt/homegames-roms`.
- Instala `config/sudoers/homegames-mount` em `/etc/sudoers.d/`, validando com `visudo -c` antes de aplicar. A regra libera **somente** `mount -t cifs .../mnt/homegames-roms ...` e `umount /mnt/homegames-roms` sem senha para o usuário do serviço — não é sudo livre, o destino do mount está fixo no comando.

**Credenciais**: a senha do Samba nunca é persistida em texto plano no `config/storage.json` exposto via `GET /config` — ela vai para `/etc/samba/homegames-credentials` (`chmod 600`, só root lê), no mesmo padrão validado manualmente antes de ser automatizado pela API.

**Trocar de storage limpa o catálogo e re-escaneia.** O scanner grava `launch_file`/`path` como strings absolutas, únicas no SQLite — se a raiz mudar (local → rede ou vice-versa), jogos antigos ficam órfãos (apontam pra um path que não existe mais). Por isso `POST /storage/local` e `POST /storage/cifs` sempre apagam a tabela `games` antes de re-escanear, em vez de tentar migrar paths relativos (over-engineering para o escopo doméstico/single-user deste projeto).

**Validado no hardware real**: pendrive ext4 compartilhado via Samba por um roteador OpenWrt, montado pelo HomeGames, jogo escaneado e jogado via streaming normalmente. Durante o teste, dois problemas foram encontrados e resolvidos **na configuração do Samba/OpenWrt** (não no HomeGames):

- `invalid users = root` no `smb.conf` do OpenWrt bloqueia explicitamente login como `root` via Samba (boa prática de segurança) — a senha definida via `smbpasswd -a root` nunca seria aceita por esse motivo. Solução: criar um usuário Unix não-root (`useradd`, pacote `shadow-useradd` se `useradd` não existir) e dar a ele uma senha Samba própria via `smbpasswd -a <usuario>`.
- Mesmo com o usuário certo, `smbpasswd -a` pode "completar sem erro" sem de fato cadastrar o usuário no backend (`passdb backend = smbpasswd`) — confirme sempre com `pdbedit -L` que o usuário aparece listado antes de assumir que a senha está correta.
- Subpastas criadas depois de um `chown -R` na pasta raiz do share não herdam o dono automaticamente — qualquer pasta nova continua `root:root` até receber seu próprio `chown`.

Se o share tiver outras pastas além das ROMs (Filmes, Músicas, etc.), o campo opcional de subpasta no formulário (ex: `Games`) evita escanear o share inteiro — CIFS sempre monta o share completo, então a subpasta é resolvida em código (`effective_roms_dir()`), não no comando de mount.

## Scanner de ROMs — regras

- Varre `<console>/` dentro do storage ativo (`emulator/roms/` por padrão, ou o ponto de montagem CIFS configurado — ver [Storage de ROMs via rede](#storage-de-roms-via-rede-cifssamba)).
- Para PS1: lista apenas `.cue`, `.chd`, `.pbp`.
- Ignora `.bin`, `.ccd`, `.sub`, `.ecm` e qualquer outro arquivo auxiliar.
- Cada arquivo de jogo válido se torna (ou atualiza) um registro na tabela `games` do SQLite, identificado pelo `launch_file`.

## Licença

[MIT](LICENSE) — uso, modificação e redistribuição livres, incluindo para fins comerciais, contanto que o aviso de copyright e a licença sejam mantidos. Contribuições da comunidade são bem-vindas.
