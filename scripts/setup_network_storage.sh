#!/usr/bin/env bash
# Configura o Raspberry Pi para montar um storage de ROMs via rede
# (CIFS/Samba), usado pelo servico backend/app/services/storage.py para
# trocar a fonte de ROMs sem reiniciar o backend.
#
# Idempotente: pode ser executado mais de uma vez sem duplicar configuracao.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SUDOERS_SRC="$PROJECT_ROOT/config/sudoers/homegames-mount"
SUDOERS_DEST="/etc/sudoers.d/homegames-mount"
MOUNT_POINT="/mnt/homegames-roms"

echo "==> Instalando cifs-utils via apt"
sudo apt-get install -y cifs-utils

echo "==> Garantindo ponto de montagem $MOUNT_POINT"
sudo mkdir -p "$MOUNT_POINT"

echo "==> Instalando regra sudoers (mount/umount com escopo minimo)"
if [[ ! -f "$SUDOERS_DEST" ]] || ! diff -q "$SUDOERS_SRC" "$SUDOERS_DEST" >/dev/null 2>&1; then
    TMP_SUDOERS="$(mktemp)"
    cp "$SUDOERS_SRC" "$TMP_SUDOERS"
    if sudo visudo -c -f "$TMP_SUDOERS" >/dev/null; then
        sudo cp "$TMP_SUDOERS" "$SUDOERS_DEST"
        sudo chmod 440 "$SUDOERS_DEST"
        echo "    Regra instalada e validada."
    else
        echo "    ERRO: regra sudoers invalida, nao aplicada. Veja $TMP_SUDOERS"
        rm -f "$TMP_SUDOERS"
        exit 1
    fi
    rm -f "$TMP_SUDOERS"
else
    echo "    Ja instalada, nada a fazer."
fi

echo "==> Concluido. Teste: sudo -n mount -t cifs --help > /dev/null && echo OK"
