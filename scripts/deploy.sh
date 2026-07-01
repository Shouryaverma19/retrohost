#!/usr/bin/env bash
# Sincroniza o projeto local com o Raspberry Pi via rsync sobre SSH.
#
# Uso:
#   RETROHOST_PI_USER=pi RETROHOST_PI_HOST=192.168.1.x ./scripts/deploy.sh
#   ./scripts/deploy.sh <ip>
#
# Não hardcoda credenciais: usa apenas o host/IP, autenticação via chave SSH
# ou prompt de senha interativo do próprio ssh/rsync.
set -euo pipefail

PI_USER="${RETROHOST_PI_USER:-pi}"
PI_HOST="${1:-${RETROHOST_PI_HOST:-}}"
PI_PATH="${RETROHOST_PI_PATH:-/home/${PI_USER}/retrohost/}"

if [[ -z "$PI_HOST" ]]; then
    echo "Erro: informe o host do Raspberry Pi." >&2
    echo "Uso: RETROHOST_PI_HOST=<ip> $0   ou   $0 <ip>" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rsync -avz --progress \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude "__pycache__/" \
    --exclude "*.pyc" \
    --exclude "*.db" \
    --exclude "*-credentials" \
    --exclude "*-credenciais" \
    "$SCRIPT_DIR/" "${PI_USER}@${PI_HOST}:${PI_PATH}"

echo "Deploy concluído para ${PI_USER}@${PI_HOST}:${PI_PATH}"
