#!/usr/bin/env bash
# Configura o Raspberry Pi para expor um teclado virtual via Linux uinput,
# usado pelo InputProvider (backend/app/input/uinput_keyboard.py) para
# traduzir botoes de gamepad recebidos do navegador em teclas que o
# RetroArch ja le via input_driver=udev.
#
# Idempotente: pode ser executado mais de uma vez sem duplicar configuracao.
# Nao requer reboot — modprobe + udevadm trigger aplicam a permissao em runtime.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UDEV_RULE_SRC="$PROJECT_ROOT/config/udev/99-uinput.rules"
UDEV_RULE_DEST="/etc/udev/rules.d/99-uinput.rules"

echo "==> Instalando python3-evdev via apt"
sudo apt-get install -y python3-evdev

echo "==> Garantindo modulo uinput carregado e persistente no boot"
if ! lsmod | grep -q '^uinput'; then
    sudo modprobe uinput
fi
if [[ ! -f /etc/modules-load.d/uinput.conf ]]; then
    echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf > /dev/null
fi

echo "==> Instalando regra udev para /dev/uinput"
if [[ ! -f "$UDEV_RULE_DEST" ]] || ! diff -q "$UDEV_RULE_SRC" "$UDEV_RULE_DEST" >/dev/null 2>&1; then
    sudo cp "$UDEV_RULE_SRC" "$UDEV_RULE_DEST"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --name-match=uinput
    echo "    Regra instalada e aplicada."
else
    echo "    Ja instalada, nada a fazer."
fi

echo "==> Permissao atual de /dev/uinput:"
ls -l /dev/uinput

echo "==> Recriando venv do backend com --system-site-packages (acesso a python3-evdev)"
cd "$PROJECT_ROOT/backend"
if [[ -f .venv/pyvenv.cfg ]] && grep -q "include-system-site-packages = true" .venv/pyvenv.cfg; then
    echo "    venv ja configurada, nada a fazer."
else
    rm -rf .venv
    python3 -m venv --system-site-packages .venv
    .venv/bin/pip install -r requirements.txt
    echo "    venv recriada com acesso a system-site-packages."
fi

echo "==> Concluido. Teste: .venv/bin/python -c 'import evdev; print(evdev.__version__)'"
