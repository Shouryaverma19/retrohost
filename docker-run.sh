#!/usr/bin/env bash
# Helper to run the RetroHost container on Linux with all required flags.
#
# Prerequisites on the host:
#   - Docker Engine installed
#   - For NVIDIA (NVENC): nvidia-container-toolkit installed
#   - Image built: docker build -t retrohost .
#
# Usage:
#   RETROHOST_WEBRTC_HOST=192.168.1.100 ./docker-run.sh
#   RETROHOST_WEBRTC_HOST=192.168.1.100 RETROHOST_GPU=nvidia ./docker-run.sh
set -euo pipefail

IMAGE="${RETROHOST_IMAGE:-retrohost}"
WEBRTC_HOST="${RETROHOST_WEBRTC_HOST:-}"
GPU="${RETROHOST_GPU:-none}"

GPU_ARGS=()
case "$GPU" in
    nvidia) GPU_ARGS=(--gpus all) ;;
    dri)    GPU_ARGS=(--device /dev/dri) ;;
    none)   GPU_ARGS=() ;;
    *) echo "RETROHOST_GPU invalid: $GPU (use nvidia|dri|none)" >&2; exit 1 ;;
esac

ENCODER_ARGS=()
[[ -n "${RETROHOST_ENCODER:-}" ]] && ENCODER_ARGS=(-e "HOMEGAMES_ENCODER=$RETROHOST_ENCODER")

exec docker run --rm -it \
    --name retrohost \
    --privileged \
    "${GPU_ARGS[@]}" \
    "${ENCODER_ARGS[@]}" \
    -e HOMEGAMES_WEBRTC_HOST="$WEBRTC_HOST" \
    -p 8000:8000 \
    -p 8889:8889 \
    -p 8554:8554 \
    -p 8189:8189/udp \
    -v retrohost-data:/data \
    "$IMAGE"
