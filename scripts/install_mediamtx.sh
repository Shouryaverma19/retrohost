#!/usr/bin/env bash
# Baixa o binário mediamtx (ARMv7) para bin/mediamtx.
# mediamtx não é distribuído via apt; baixamos o release oficial do GitHub.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$PROJECT_ROOT/bin"
VERSION="${MEDIAMTX_VERSION:-v1.19.2}"
ASSET="mediamtx_${VERSION}_linux_armv7.tar.gz"
URL="https://github.com/bluenviron/mediamtx/releases/download/${VERSION}/${ASSET}"

mkdir -p "$BIN_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Baixando ${URL}..."
curl -sL -o "$TMP_DIR/$ASSET" "$URL"
tar -xzf "$TMP_DIR/$ASSET" -C "$TMP_DIR" mediamtx
mv "$TMP_DIR/mediamtx" "$BIN_DIR/mediamtx"
chmod +x "$BIN_DIR/mediamtx"

echo "Instalado em $BIN_DIR/mediamtx ($("$BIN_DIR/mediamtx" --version))"
