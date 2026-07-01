#!/usr/bin/env bash
# Helper para rodar o container HomeGames no Docker Desktop (Windows + WSL2).
#
# A imagem é AGNÓSTICA DE GPU: o encoder de vídeo é auto-detectado (nvenc > qsv >
# vaapi > libx264). As flags de GPU abaixo são OPCIONAIS — sem nenhuma, cai para
# libx264 (CPU) e sobe igual. Tudo isolado no container, nada instalado no host.
#
#  --gpus all        : NVIDIA (NVENC). Requer runtime nvidia no Docker Desktop.
#  --device /dev/dri : Intel/AMD (QSV/VAAPI). No WSL2 a GPU pode aparecer em
#                      /dev/dri via dxcore; VAAPI no WSL2 é instavel, entao se
#                      falhar a deteccao cai para CPU automaticamente.
#  --privileged      : necessario para o mount -t cifs do storage de rede.
#  SEM --device /dev/snd : WSL2 nao expoe audio; o container usa PulseAudio
#                      null-sink interno (evita fast-forward sem placa de som).
#
# Controle por env:
#  HOMEGAMES_GPU=nvidia|dri|none  (default: nvidia) — qual flag de GPU usar.
#  HOMEGAMES_ENCODER=...          — forca um encoder (override da auto-deteccao).
#  HOMEGAMES_WEBRTC_HOST=<ip LAN> — IP do host p/ WebRTC multi-device.
#
# Pre-requisitos: Docker Desktop. Imagem buildada: docker build -t homegames .
set -euo pipefail

IMAGE="${HOMEGAMES_IMAGE:-homegames}"
WEBRTC_HOST="${HOMEGAMES_WEBRTC_HOST:-}"
GPU="${HOMEGAMES_GPU:-nvidia}"

GPU_ARGS=()
case "$GPU" in
    nvidia) GPU_ARGS=(--gpus all) ;;
    dri)    GPU_ARGS=(--device /dev/dri) ;;
    none)   GPU_ARGS=() ;;
    *) echo "HOMEGAMES_GPU invalido: $GPU (use nvidia|dri|none)" >&2; exit 1 ;;
esac

ENCODER_ARGS=()
[[ -n "${HOMEGAMES_ENCODER:-}" ]] && ENCODER_ARGS=(-e "HOMEGAMES_ENCODER=$HOMEGAMES_ENCODER")

# Acesse a UI por http://<WEBRTC_HOST>:8000 (nao localhost) para o video
# funcionar tambem em outros dispositivos da rede.
exec docker run --rm -it \
    --name homegames \
    --privileged \
    "${GPU_ARGS[@]}" \
    "${ENCODER_ARGS[@]}" \
    -e HOMEGAMES_WEBRTC_HOST="$WEBRTC_HOST" \
    -p 8000:8000 \
    -p 8889:8889 \
    -p 8554:8554 \
    -p 8189:8189/udp \
    -v homegames-data:/data \
    "$IMAGE"
