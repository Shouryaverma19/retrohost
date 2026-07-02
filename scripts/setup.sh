#!/usr/bin/env bash
# RetroHost — setup completo para Raspberry Pi.
#
# Uso (a partir da raiz do projeto clonado):
#   bash scripts/setup.sh
#
# O que este script faz:
#   1. Verifica dependências do sistema (retroarch, ffmpeg, python3, git)
#   2. Configura RetroArch para modo headless (sem TV/monitor)
#   3. Baixa o MediaMTX (servidor WebRTC/WHEP)
#   4. Instala e configura o input remoto via uinput
#   5. Cria e instala o venv Python com as dependências do backend
#   6. Compila o core PS1 (PCSX-ReARMed) do source, se ainda não presente
#   7. Instala os serviços systemd (mediamtx + retrohost)
#   8. (Opcional) Configura storage de ROMs via rede (CIFS/Samba)
#   9. Inicia os serviços e valida a instalação
#
# Idempotente: pode ser executado mais de uma vez sem problemas.
# Requer sudo para: apt-get, systemd, udev, sudoers, /boot/firmware/config.txt
set -euo pipefail

# ---------------------------------------------------------------------------
# Cores e helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BOLD}==>${NC} $*"; }
ok()      { echo -e "    ${GREEN}✓${NC} $*"; }
warn()    { echo -e "    ${YELLOW}!${NC} $*"; }
error()   { echo -e "    ${RED}✗${NC} $*" >&2; }
ask()     { echo -e "${BOLD}?${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}RetroHost — setup para Raspberry Pi${NC}"
echo "Projeto em: $PROJECT_ROOT"
echo ""

# ---------------------------------------------------------------------------
# 1. Verificar plataforma
# ---------------------------------------------------------------------------
info "Verificando plataforma..."

if [[ "$(uname -s)" != "Linux" ]]; then
    error "Este script é para Linux (Raspberry Pi OS). Use Docker para outros sistemas."
    exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "armv7l" && "$ARCH" != "aarch64" ]]; then
    warn "Arquitetura '$ARCH' não é ARM — este setup é para Raspberry Pi."
    warn "Para x86_64, use o Docker (ver README.md)."
    read -r -p "    Continuar mesmo assim? [s/N] " CONFIRM
    [[ "${CONFIRM,,}" == "s" ]] || exit 1
fi

ok "Plataforma: $(uname -s) $ARCH"

# ---------------------------------------------------------------------------
# 2. Detectar usuário e diretório de instalação
# ---------------------------------------------------------------------------
info "Configuração de usuário..."

CURRENT_USER="${SUDO_USER:-$(whoami)}"
DEFAULT_INSTALL_DIR="/home/$CURRENT_USER/retrohost"

ask "Usuário do sistema [$CURRENT_USER]: "
read -r INPUT_USER
INSTALL_USER="${INPUT_USER:-$CURRENT_USER}"

ask "Diretório de instalação [$DEFAULT_INSTALL_DIR]: "
read -r INPUT_DIR
INSTALL_DIR="${INPUT_DIR:-$DEFAULT_INSTALL_DIR}"

if [[ "$INSTALL_DIR" != "$PROJECT_ROOT" ]]; then
    warn "O projeto foi clonado em '$PROJECT_ROOT' mas o diretório de instalação é '$INSTALL_DIR'."
    warn "Os arquivos .service usarão '$INSTALL_DIR'. Certifique-se de que o projeto está lá."
fi

ok "Usuário: $INSTALL_USER"
ok "Diretório: $INSTALL_DIR"

# ---------------------------------------------------------------------------
# 3. Verificar dependências do sistema
# ---------------------------------------------------------------------------
info "Verificando dependências do sistema..."

MISSING=()
for cmd in retroarch ffmpeg python3 curl git; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING+=("$cmd")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    warn "Dependências faltando: ${MISSING[*]}"
    info "Instalando dependências via apt..."
    sudo apt-get update -qq
    PKG_MAP=( "retroarch:retroarch" "ffmpeg:ffmpeg" "python3:python3-venv" "curl:curl" "git:git" )
    PKGS_TO_INSTALL=()
    for entry in "${PKG_MAP[@]}"; do
        cmd="${entry%%:*}"; pkg="${entry##*:}"
        if [[ " ${MISSING[*]} " == *" $cmd "* ]]; then
            PKGS_TO_INSTALL+=("$pkg")
        fi
    done
    sudo apt-get install -y --no-install-recommends "${PKGS_TO_INSTALL[@]}"
fi

ok "retroarch: $(retroarch --version 2>&1 | head -1)"
ok "ffmpeg: $(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3)"
ok "python3: $(python3 --version)"

# ---------------------------------------------------------------------------
# 4. Configurar RetroArch headless
# ---------------------------------------------------------------------------
info "Configurando RetroArch para modo headless..."

BOOT_CONFIG="/boot/firmware/config.txt"
RETROARCH_CFG="$HOME/.config/retroarch/retroarch.cfg"

# Gera o retroarch.cfg se não existir
if [[ ! -f "$RETROARCH_CFG" ]]; then
    warn "retroarch.cfg não encontrado. Gerando..."
    mkdir -p "$(dirname "$RETROARCH_CFG")"
    retroarch --headless 2>/dev/null || true
fi

if [[ ! -f "$RETROARCH_CFG" ]]; then
    warn "Não foi possível gerar o retroarch.cfg automaticamente."
    warn "Rode 'retroarch' uma vez manualmente e execute este script novamente."
    mkdir -p "$(dirname "$RETROARCH_CFG")"
    touch "$RETROARCH_CFG"
fi

set_cfg_key() {
    local key="$1" value="$2"
    if grep -qE "^${key} = " "$RETROARCH_CFG" 2>/dev/null; then
        sed -i "s|^${key} = .*|${key} = \"${value}\"|" "$RETROARCH_CFG"
    else
        echo "${key} = \"${value}\"" >> "$RETROARCH_CFG"
    fi
}

set_cfg_key "video_driver"         "null"
set_cfg_key "video_context_driver" ""
set_cfg_key "video_shader_enable"  "false"
set_cfg_key "input_driver"         "udev"
set_cfg_key "audio_driver"         "alsa"

ok "retroarch.cfg configurado ($RETROARCH_CFG)"

# Configura /boot/firmware/config.txt (força detecção de display headless)
if [[ -f "$BOOT_CONFIG" ]]; then
    if ! grep -q "^hdmi_force_hotplug=1" "$BOOT_CONFIG"; then
        sudo cp "$BOOT_CONFIG" "${BOOT_CONFIG}.bak.$(date +%s)"
        sudo tee -a "$BOOT_CONFIG" > /dev/null <<'EOF'

# RetroHost: força detecção de display mesmo sem TV conectada (headless)
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=85
EOF
        warn "Adicionado hdmi_force_hotplug ao $BOOT_CONFIG."
        NEEDS_REBOOT=1
    else
        ok "$BOOT_CONFIG já configurado"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Baixar MediaMTX
# ---------------------------------------------------------------------------
info "Instalando MediaMTX (servidor WebRTC/WHEP)..."

BIN_DIR="$PROJECT_ROOT/bin"
MEDIAMTX_BIN="$BIN_DIR/mediamtx"
MEDIAMTX_VERSION="${MEDIAMTX_VERSION:-v1.19.2}"

if [[ -f "$MEDIAMTX_BIN" ]]; then
    ok "MediaMTX já instalado ($("$MEDIAMTX_BIN" --version 2>&1 | head -1))"
else
    # Detecta asset correto por arquitetura
    case "$ARCH" in
        armv7l)  ASSET="mediamtx_${MEDIAMTX_VERSION}_linux_armv7.tar.gz" ;;
        aarch64) ASSET="mediamtx_${MEDIAMTX_VERSION}_linux_arm64v8.tar.gz" ;;
        x86_64)  ASSET="mediamtx_${MEDIAMTX_VERSION}_linux_amd64.tar.gz" ;;
        *)       error "Arquitetura '$ARCH' não suportada para MediaMTX."; exit 1 ;;
    esac
    URL="https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/${ASSET}"

    mkdir -p "$BIN_DIR"
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT

    info "  Baixando $ASSET..."
    curl -sL -o "$TMP_DIR/$ASSET" "$URL"
    tar -xzf "$TMP_DIR/$ASSET" -C "$TMP_DIR" mediamtx
    mv "$TMP_DIR/mediamtx" "$MEDIAMTX_BIN"
    chmod +x "$MEDIAMTX_BIN"

    ok "MediaMTX instalado ($("$MEDIAMTX_BIN" --version 2>&1 | head -1))"
fi

# ---------------------------------------------------------------------------
# 6. Configurar input remoto (uinput)
# ---------------------------------------------------------------------------
info "Configurando input remoto via uinput..."

sudo apt-get install -y --no-install-recommends python3-evdev -qq

if ! lsmod | grep -q '^uinput'; then
    sudo modprobe uinput
fi
if [[ ! -f /etc/modules-load.d/uinput.conf ]]; then
    echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf > /dev/null
fi

UDEV_RULE_SRC="$PROJECT_ROOT/config/udev/99-uinput.rules"
UDEV_RULE_DEST="/etc/udev/rules.d/99-uinput.rules"
if [[ ! -f "$UDEV_RULE_DEST" ]] || ! diff -q "$UDEV_RULE_SRC" "$UDEV_RULE_DEST" &>/dev/null; then
    sudo cp "$UDEV_RULE_SRC" "$UDEV_RULE_DEST"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --name-match=uinput
fi

ok "uinput configurado ($(ls -l /dev/uinput | awk '{print $1, $3, $4}'))"

# ---------------------------------------------------------------------------
# 7. Criar venv Python e instalar dependências
# ---------------------------------------------------------------------------
info "Configurando ambiente Python do backend..."

VENV_DIR="$PROJECT_ROOT/backend/.venv"

if [[ -f "$VENV_DIR/pyvenv.cfg" ]] && grep -q "include-system-site-packages = true" "$VENV_DIR/pyvenv.cfg"; then
    ok "venv já configurado com system-site-packages"
else
    rm -rf "$VENV_DIR"
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --quiet -r "$PROJECT_ROOT/backend/requirements.txt"
ok "Dependências instaladas (fastapi, uvicorn, sqlalchemy, pydantic...)"

# ---------------------------------------------------------------------------
# 8. Compilar PCSX-ReARMed (core PS1), se ainda não presente
# ---------------------------------------------------------------------------
# PCSX-ReARMed não tem pacote apt no Raspberry Pi OS (diferente do Beetle PSX
# usado no Docker/x86_64) e é bem mais leve para o hardware do Pi, então
# compilamos do source direto para emulator/cores/.
PS1_CORE_DEST="$PROJECT_ROOT/emulator/cores/pcsx_rearmed_libretro.so"

if [[ ! -f "$PS1_CORE_DEST" ]]; then
    info "Compilando core PS1 (PCSX-ReARMed) do source..."

    sudo apt-get install -y --no-install-recommends build-essential git -qq

    # Mapeia modelo do Pi + arquitetura para o alvo 'platform=' do Makefile.
    # Ver Makefile.libretro do pcsx_rearmed para a lista de plataformas.
    PI_MODEL="$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo '')"
    PCSX_PLATFORM=""
    case "$PI_MODEL" in
        *"Raspberry Pi 5"*)   PCSX_PLATFORM="rpi4_64" ;;   # sem alvo dedicado; rpi4_64 é o mais próximo (arm64, ari64)
        *"Raspberry Pi 4"*)   [[ "$ARCH" == "aarch64" ]] && PCSX_PLATFORM="rpi4_64" || PCSX_PLATFORM="rpi4" ;;
        *"Raspberry Pi 3"*)   [[ "$ARCH" == "aarch64" ]] && PCSX_PLATFORM="rpi3_64" || PCSX_PLATFORM="rpi3" ;;
        *"Raspberry Pi 2"*)   PCSX_PLATFORM="rpi2" ;;
        *"Raspberry Pi Model"*|*"Raspberry Pi Zero"*) PCSX_PLATFORM="rpi1" ;;
        *)
            warn "Modelo de Pi não reconhecido ('$PI_MODEL') — usando alvo genérico."
            [[ "$ARCH" == "aarch64" ]] && PCSX_PLATFORM="rpi3_64" || PCSX_PLATFORM="rpi2"
            ;;
    esac
    ok "Alvo de build detectado: platform=$PCSX_PLATFORM ($PI_MODEL, $ARCH)"

    PCSX_SRC_DIR="$PROJECT_ROOT/emulator/pcsx_rearmed_src"
    if [[ ! -d "$PCSX_SRC_DIR" ]]; then
        git clone --depth 1 --recursive \
            https://github.com/libretro/pcsx_rearmed.git "$PCSX_SRC_DIR"
    fi

    if ( cd "$PCSX_SRC_DIR" && make -f Makefile.libretro "platform=$PCSX_PLATFORM" -j"$(nproc)" ); then
        mkdir -p "$PROJECT_ROOT/emulator/cores"
        cp "$PCSX_SRC_DIR/pcsx_rearmed_libretro.so" "$PS1_CORE_DEST"
        ok "Core PS1 compilado: $PS1_CORE_DEST"
    else
        error "Falha ao compilar PCSX-ReARMed. Veja $PCSX_SRC_DIR para depurar."
        warn "cores.json ficará sem 'ps1' — configure manualmente depois."
    fi
else
    ok "Core PS1 já compilado ($PS1_CORE_DEST)"
fi

# ---------------------------------------------------------------------------
# 9. Configurar cores.json
# ---------------------------------------------------------------------------
info "Configurando mapeamento de cores libretro..."

CORES_JSON="$PROJECT_ROOT/config/cores.json"
CORES_EXAMPLE="$PROJECT_ROOT/config/cores.json.example"

if [[ ! -f "$CORES_JSON" ]]; then
    # Detecta cores instalados via apt automaticamente
    LIBRETRO_DIRS=(
        "/usr/lib/arm-linux-gnueabihf/libretro"
        "/usr/lib/aarch64-linux-gnu/libretro"
        "/usr/lib/x86_64-linux-gnu/libretro"
    )
    LIBRETRO_DIR=""
    for d in "${LIBRETRO_DIRS[@]}"; do
        [[ -d "$d" ]] && LIBRETRO_DIR="$d" && break
    done

    # Procura cores conhecidos
    PS1_CORE=""
    SNES_CORE=""

    # PS1: primeiro o compilado acima, depois qualquer core PS1 já instalado via apt
    [[ -f "$PS1_CORE_DEST" ]] && PS1_CORE="$PS1_CORE_DEST"
    [[ -z "$PS1_CORE" && -n "$LIBRETRO_DIR" && -f "$LIBRETRO_DIR/pcsx_rearmed_libretro.so" ]] && \
        PS1_CORE="$LIBRETRO_DIR/pcsx_rearmed_libretro.so"

    # SNES: bsnes-mercury (apt) ou snes9x
    for candidate in \
        "$PROJECT_ROOT/emulator/cores/snes9x_libretro.so" \
        "${LIBRETRO_DIR:-/dev/null}/bsnes_mercury_performance_libretro.so" \
        "${LIBRETRO_DIR:-/dev/null}/snes9x_libretro.so"
    do
        [[ -f "$candidate" ]] && SNES_CORE="$candidate" && break
    done

    {
        echo "{"
        FIRST=1
        write_entry() {
            local key="$1" path="$2"
            [[ -z "$path" ]] && return
            [[ $FIRST -eq 0 ]] && echo ","
            printf '  "%s": "%s"' "$key" "$path"
            FIRST=0
        }
        write_entry "ps1"  "$PS1_CORE"
        write_entry "snes" "$SNES_CORE"
        echo ""
        echo "}"
    } > "$CORES_JSON"

    if [[ -n "$PS1_CORE" || -n "$SNES_CORE" ]]; then
        ok "cores.json gerado automaticamente:"
        [[ -n "$PS1_CORE"  ]] && ok "  ps1  → $PS1_CORE"
        [[ -n "$SNES_CORE" ]] && ok "  snes → $SNES_CORE"
    else
        warn "Nenhum core detectado automaticamente."
        warn "Edite $CORES_JSON manualmente com os paths dos seus cores .so"
        warn "Exemplo em $CORES_EXAMPLE"
    fi
else
    ok "cores.json já existe — mantendo"
fi

# ---------------------------------------------------------------------------
# 10. (Opcional) Storage de ROMs via rede (CIFS/Samba)
# ---------------------------------------------------------------------------
echo ""
ask "Configurar storage de ROMs via rede (CIFS/Samba)? [s/N]: "
read -r SETUP_CIFS

if [[ "${SETUP_CIFS,,}" == "s" ]]; then
    info "Configurando storage CIFS..."

    sudo apt-get install -y --no-install-recommends cifs-utils -qq

    MOUNT_POINT="/mnt/homegames-roms"
    sudo mkdir -p "$MOUNT_POINT"

    SUDOERS_SRC="$PROJECT_ROOT/config/sudoers/homegames-mount"
    SUDOERS_DEST="/etc/sudoers.d/homegames-mount"

    # Substitui YOUR_USER pelo usuário real antes de instalar
    TMP_SUDOERS="$(mktemp)"
    sed "s/YOUR_USER/$INSTALL_USER/g" "$SUDOERS_SRC" > "$TMP_SUDOERS"

    if sudo visudo -c -f "$TMP_SUDOERS" &>/dev/null; then
        sudo cp "$TMP_SUDOERS" "$SUDOERS_DEST"
        sudo chmod 440 "$SUDOERS_DEST"
        ok "Regra sudoers instalada para $INSTALL_USER"
    else
        error "Regra sudoers inválida — não aplicada"
    fi
    rm -f "$TMP_SUDOERS"

    ok "CIFS configurado. Use 'Configurar storage' na interface web para apontar para o share."
else
    ok "Storage CIFS ignorado — usando ROMs locais em $PROJECT_ROOT/emulator/roms/"
fi

# ---------------------------------------------------------------------------
# 11. Instalar serviços systemd
# ---------------------------------------------------------------------------
info "Instalando serviços systemd..."

for SERVICE in mediamtx homegames; do
    SRC="$PROJECT_ROOT/scripts/${SERVICE}.service"
    DEST="/etc/systemd/system/${SERVICE}.service"

    # Substitui YOUR_USER e /home/YOUR_USER/retrohost pelo real
    TMP_SERVICE="$(mktemp)"
    sed \
        -e "s|YOUR_USER|$INSTALL_USER|g" \
        -e "s|/home/YOUR_USER/retrohost|$INSTALL_DIR|g" \
        "$SRC" > "$TMP_SERVICE"

    sudo cp "$TMP_SERVICE" "$DEST"
    rm -f "$TMP_SERVICE"
    ok "$SERVICE.service instalado"
done

sudo systemctl daemon-reload
sudo systemctl enable mediamtx homegames
ok "Serviços habilitados para iniciar no boot"

# ---------------------------------------------------------------------------
# 12. Iniciar serviços
# ---------------------------------------------------------------------------
info "Iniciando serviços..."

sudo systemctl restart mediamtx
sleep 2
sudo systemctl restart homegames
sleep 2

MEDIAMTX_STATUS="$(systemctl is-active mediamtx 2>/dev/null || echo 'inativo')"
HOMEGAMES_STATUS="$(systemctl is-active homegames 2>/dev/null || echo 'inativo')"

if [[ "$MEDIAMTX_STATUS" == "active" ]]; then
    ok "mediamtx: ativo"
else
    error "mediamtx: $MEDIAMTX_STATUS (veja: journalctl -u mediamtx -n 20)"
fi

if [[ "$HOMEGAMES_STATUS" == "active" ]]; then
    ok "homegames (API): ativo"
else
    error "homegames: $HOMEGAMES_STATUS (veja: journalctl -u homegames -n 20)"
fi

# ---------------------------------------------------------------------------
# 13. Validação final
# ---------------------------------------------------------------------------
info "Validando instalação..."

sleep 1
HTTP_STATUS="$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo '000')"

if [[ "$HTTP_STATUS" == "200" ]]; then
    ok "API respondendo em http://localhost:8000/health"
else
    warn "API ainda não respondeu (HTTP $HTTP_STATUS) — pode precisar de alguns segundos"
    warn "Teste: curl http://localhost:8000/health"
fi

# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  RetroHost configurado!${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""
echo "  Acesse: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "  Próximos passos:"
echo "  1. Coloque as ROMs em: $PROJECT_ROOT/emulator/roms/<console>/"
echo "  2. Clique 'Escanear biblioteca' na interface web"
if [[ -z "${PS1_CORE:-}" && -z "${SNES_CORE:-}" ]]; then
    echo "  3. Configure os cores em: $PROJECT_ROOT/config/cores.json"
fi
echo ""
echo "  Logs:"
echo "    journalctl -u homegames -f"
echo "    journalctl -u mediamtx -f"
echo ""

if [[ "${NEEDS_REBOOT:-0}" == "1" ]]; then
    echo -e "  ${YELLOW}⚠ REBOOT NECESSÁRIO${NC} para aplicar as configurações de HDMI headless:"
    echo "    sudo reboot"
    echo ""
fi
