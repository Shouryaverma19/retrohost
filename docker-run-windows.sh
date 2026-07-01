#!/usr/bin/env bash
# Helper to run the RetroHost container on Docker Desktop (Windows + WSL2).
#
# The image is GPU-agnostic: the video encoder is auto-detected at startup
# (nvenc > qsv > vaapi > libx264). GPU flags below are OPTIONAL — without
# any GPU flag the encoder falls back to libx264 (CPU) and the container
# starts normally on any machine.
#
# Prerequisites: Docker Desktop installed. Image built: docker build -t retrohost .
#
# Usage:
#   RETROHOST_WEBRTC_HOST=192.168.1.100 ./docker-run-windows.sh
#   RETROHOST_WEBRTC_HOST=192.168.1.100 RETROHOST_GPU=nvidia ./docker-run-windows.sh
#
# Environment variables:
#   RETROHOST_WEBRTC_HOST  LAN IP of this machine (required for multi-device WebRTC)
#   RETROHOST_GPU          nvidia | dri | none  (default: none)
#   RETROHOST_ENCODER      Force a specific encoder, e.g. libx264 (overrides auto-detect)
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

# Access the UI at http://<RETROHOST_WEBRTC_HOST>:8000 (not localhost)
# for WebRTC video to work on other devices on your LAN.
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
