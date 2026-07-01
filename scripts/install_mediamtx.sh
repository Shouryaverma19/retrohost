#!/usr/bin/env bash
# Baixa o binário mediamtx para bin/mediamtx e verifica SHA-256.
# mediamtx não é distribuído via apt; baixamos o release oficial do GitHub.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$PROJECT_ROOT/bin"
VERSION="${MEDIAMTX_VERSION:-v1.19.2}"

# SHA-256 conhecidos para v1.19.2 (calculados a partir do release oficial).
# Atualize estes hashes ao trocar VERSION.
declare -A KNOWN_SHA256=(
    ["linux_armv7"]="de0afed5ba33df231a6c3321207b4a906f1da9be7ce8b3efac008928e982ca6d"
    ["linux_arm64v8"]="0019dfc4b32d63c1392aa264aed2253c1e0c2fb09216f8e2cc269bbfb8bb49b5"
    ["linux_amd64"]="f9c601cc303ceca8fad2883917b022882672c5bc56311e92dbceb16e5f20c60c"
)

ARCH="$(uname -m)"
case "$ARCH" in
    armv7l)  PLATFORM="linux_armv7" ;;
    aarch64) PLATFORM="linux_arm64v8" ;;
    x86_64)  PLATFORM="linux_amd64" ;;
    *) echo "Arquitetura '$ARCH' não suportada." >&2; exit 1 ;;
esac

ASSET="mediamtx_${VERSION}_${PLATFORM}.tar.gz"
URL="https://github.com/bluenviron/mediamtx/releases/download/${VERSION}/${ASSET}"
EXPECTED_SHA="${KNOWN_SHA256[$PLATFORM]}"

mkdir -p "$BIN_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Baixando ${URL}..."
curl -sL -o "$TMP_DIR/$ASSET" "$URL"

echo "Verificando integridade (SHA-256)..."
ACTUAL_SHA="$(sha256sum "$TMP_DIR/$ASSET" | awk '{print $1}')"
if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
    echo "ERRO: SHA-256 não confere!" >&2
    echo "  Esperado: $EXPECTED_SHA" >&2
    echo "  Obtido:   $ACTUAL_SHA" >&2
    exit 1
fi
echo "  OK: $ACTUAL_SHA"

tar -xzf "$TMP_DIR/$ASSET" -C "$TMP_DIR" mediamtx
mv "$TMP_DIR/mediamtx" "$BIN_DIR/mediamtx"
chmod +x "$BIN_DIR/mediamtx"

echo "Instalado em $BIN_DIR/mediamtx ($("$BIN_DIR/mediamtx" --version))"
