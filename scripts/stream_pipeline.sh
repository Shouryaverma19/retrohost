#!/usr/bin/env bash
# Pipeline manual de streaming: RetroArch (headless) -> FIFO -> ffmpeg
# (encoder de hardware h264_v4l2m2m + áudio opus) -> RTSP -> mediamtx (WHEP/WebRTC).
#
# Uso: ./stream_pipeline.sh <core.so> <launch_file>
# Exemplo:
#   ./stream_pipeline.sh \
#     /home/YOUR_USER/retrohost/emulator/cores/pcsx_rearmed_libretro.so \
#     "/home/YOUR_USER/retrohost/emulator/roms/ps1/Dino Crisis (v1.1)/Dino Crisis (v1.1).cue"
#
# Pré-requisitos: scripts/setup_streaming.sh já executado (e Pi rebotado),
# mediamtx já rodando (bin/mediamtx config/mediamtx.yml).
#
# Nota sobre codec de áudio: o RetroArch grava PCM raw (pcm_s16le) num único
# FIFO em container Matroska junto com o vídeo raw (ver
# config/retroarch/record_raw_av.cfg). O ffmpeg codifica esse áudio em Opus
# — não AAC: o mediamtx descarta trilhas AAC ao publicar via WHEP porque
# navegadores não suportam AAC nativamente em WebRTC (apenas Opus/G.711).
#
# -g 15 (GOP curto): recupera de perda de pacote mais rápido (era 30,
# causava freezes visíveis). -pkt_size 1200: evita que o mediamtx precise
# remontar pacotes RTP maiores que o MTU (1460 > 1440 observado nos logs).
set -euo pipefail

CORE="${1:?uso: stream_pipeline.sh <core.so> <launch_file>}"
LAUNCH_FILE="${2:?uso: stream_pipeline.sh <core.so> <launch_file>}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIFO=/tmp/retroarch_av.fifo
RECORDCONFIG="$PROJECT_ROOT/config/retroarch/record_raw_av.cfg"

rm -f "$FIFO"
mkfifo "$FIFO"

cleanup() {
    echo "Encerrando pipeline..."
    kill "$RETROARCH_PID" "$FFMPEG_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    rm -f "$FIFO"
}
trap cleanup EXIT INT TERM

retroarch -f -r "$FIFO" --recordconfig="$RECORDCONFIG" -L "$CORE" "$LAUNCH_FILE" &
RETROARCH_PID=$!

sleep 2

ffmpeg -y -re -i "$FIFO" \
    -c:v h264_v4l2m2m -b:v 2M -g 15 \
    -c:a libopus -b:a 96k \
    -pkt_size 1200 \
    -f rtsp rtsp://127.0.0.1:8554/live &
FFMPEG_PID=$!

echo "RetroArch PID=$RETROARCH_PID, ffmpeg PID=$FFMPEG_PID"
echo "Stream disponível via WHEP em http://<pi>:8889/live/whep"
wait "$RETROARCH_PID" "$FFMPEG_PID"
