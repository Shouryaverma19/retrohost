#!/usr/bin/env bash
# Helper para rodar o container HomeGames com todas as flags necessárias.
# Edite ROMS_DIR para apontar para a sua pasta de ROMs no host.
#
# Pré-requisitos no host:
#   - Docker + nvidia-container-toolkit (para --gpus all / NVENC)
#   - módulo uinput carregado:  sudo modprobe uinput
#   - imagem buildada:          docker build -t homegames .
set -euo pipefail

IMAGE="${HOMEGAMES_IMAGE:-homegames}"
ROMS_DIR="${HOMEGAMES_ROMS_DIR:-$HOME/roms}"

# Flags explicadas:
#  --gpus all          -> NVENC (h264_nvenc) acessa a GPU NVIDIA.
#  --device /dev/uinput-> input remoto (teclado virtual lido pelo RetroArch).
#  --device /dev/snd   -> áudio ALSA real; sem ele o jogo pode rodar em fast
#                         forward (ver ARCHITECTURE.md, risco de áudio). Remova
#                         se a sua máquina não tiver placa de som e teste o
#                         comportamento — pode exigir HOMEGAMES_AUDIO_DRIVER.
#  -p 8000             -> FastAPI + UI + sinalização WHEP/WebSocket de input.
#  -p 8889             -> WHEP (negociação WebRTC do vídeo).
#  -p 8189/udp         -> ICE/UDP do WebRTC (fluxo de mídia).
#  -p 8554             -> RTSP interno (ffmpeg -> mediamtx); útil para debug.
#  -v roms             -> biblioteca de ROMs do host (somente leitura).
#  -v homegames-data   -> persiste o SQLite (/data) entre execuções do container.
exec docker run --rm -it \
    --name homegames \
    --gpus all \
    --device /dev/uinput \
    --device /dev/snd \
    -p 8000:8000 \
    -p 8889:8889 \
    -p 8554:8554 \
    -p 8189:8189/udp \
    -v "${ROMS_DIR}:/app/emulator/roms:ro" \
    -v homegames-data:/data \
    "$IMAGE"
