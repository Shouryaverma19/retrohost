#!/usr/bin/env bash
# Entrypoint do container HomeGames (ver Dockerfile / ARCHITECTURE.md).
#
# Substitui os dois systemd units do Pi (mediamtx.service + homegames.service)
# por um supervisor leve: sobe o mediamtx em background e o uvicorn em foreground,
# encerrando o mediamtx junto quando o container recebe SIGTERM/SIGINT.
#
# Também gera, na primeira execução, o retroarch.cfg headless e um cores.json
# default — coisas que no Pi são feitas pelos scripts de setup, mas que aqui
# precisam acontecer dentro do container.
set -euo pipefail

APP_ROOT="${HOMEGAMES_ROOT:-/app}"
# HOME fixo e gravável: o RetroArch grava o cfg e (com config_save_on_exit) pode
# reescrevê-lo; /tmp é gravável e é o mesmo HOME usado pelo PulseAudio adiante.
# Exportado para que o uvicorn e os subprocessos (RetroArch) herdem o mesmo HOME.
export HOME=/tmp
RETROARCH_CFG="$HOME/.config/retroarch/retroarch.cfg"
RETROARCH_SYSTEM_DIR="$HOME/.config/retroarch/system"
CORES_JSON="$APP_ROOT/config/cores.json"
LIBRETRO_DIR="/usr/lib/x86_64-linux-gnu/libretro"

# ---------------------------------------------------------------------------
# 1. retroarch.cfg headless
# ---------------------------------------------------------------------------
# Replica o que o scripts/setup_streaming.sh faz no Pi, SEM a parte de
# /boot/firmware/config.txt (que só existe no Raspberry Pi).
#
# ÁUDIO: no Pi, audio_driver=alsa lê /dev/snd real e o clock de áudio é o que
# limita o ritmo do core; sem áudio funcional o jogo roda em "fast forward".
# No container (especialmente WSL2, que não expõe /dev/snd) usamos um
# PulseAudio com null-sink por software como clock — ver passo 3 abaixo.
# audio_driver é sobrescrevível por env HOMEGAMES_AUDIO_DRIVER (ex: =alsa numa
# máquina Linux nativa que passe /dev/snd via --device).
AUDIO_DRIVER="${HOMEGAMES_AUDIO_DRIVER:-pulse}"

# Regerado SEMPRE (não só se faltar): o RetroArch, ao sair/crashar com
# config_save_on_exit=true, sobrescreve o cfg com defaults (sem video_driver=null),
# o que quebra a próxima execução headless. config_save_on_exit="false" abaixo
# evita isso, mas regerar a cada boot garante um estado limpo.
echo "==> Gerando retroarch.cfg headless em $RETROARCH_CFG"
mkdir -p "$(dirname "$RETROARCH_CFG")" "$RETROARCH_SYSTEM_DIR"
# Driver de input: "sdl2" no container (joystick virtual SDL via LD_PRELOAD,
# nao depende de udevd que o WSL2 nao tem) ou "udev" (Pi, teclado uinput).
INPUT_PROVIDER="${HOMEGAMES_INPUT_PROVIDER:-uinput}"
if [[ "$INPUT_PROVIDER" == "sdl" ]]; then
    RA_INPUT_DRIVER="sdl2"
    RA_JOYPAD_DRIVER="sdl2"
else
    RA_INPUT_DRIVER="udev"
    RA_JOYPAD_DRIVER="udev"
fi

cat > "$RETROARCH_CFG" <<EOF
video_driver = "null"
video_context_driver = ""
video_shader_enable = "false"
input_driver = "$RA_INPUT_DRIVER"
input_joypad_driver = "$RA_JOYPAD_DRIVER"
audio_driver = "$AUDIO_DRIVER"
config_save_on_exit = "false"
system_directory = "$RETROARCH_SYSTEM_DIR"

# Binds de teclado do player 1 (RetroPad), usados no modo uinput (Pi). No modo
# SDL o input vem do joystick virtual (autoconfig), e estes binds sao inocuos.
# Sao os defaults do RetroArch, coerentes com app/input/keymap.py.
input_player1_a = "x"
input_player1_b = "z"
input_player1_x = "s"
input_player1_y = "a"
input_player1_l = "q"
input_player1_r = "w"
input_player1_start = "enter"
input_player1_select = "rshift"
input_player1_up = "up"
input_player1_down = "down"
input_player1_left = "left"
input_player1_right = "right"
EOF

# A cópia da BIOS de PS1 (necessária pelo core Beetle PSX) acontece no
# RetroArchDriver.launch() — lá o storage (CIFS) já está montado e o system
# directory (HOMEGAMES_SYSTEM_DIR, exportado abaixo) está acessível. Ver
# backend/app/drivers/retroarch.py.
export HOMEGAMES_SYSTEM_DIR="$RETROARCH_SYSTEM_DIR"

# ---------------------------------------------------------------------------
# 2. cores.json default (se nenhum for montado por volume)
# ---------------------------------------------------------------------------
# No Pi os cores estão em emulator/cores/ (paths absolutos no JSON). No container
# os cores vêm do apt em $LIBRETRO_DIR. Se o usuário não montou um cores.json
# próprio, geramos um apontando para os cores instalados que existirem.
if [[ ! -f "$CORES_JSON" ]]; then
    echo "==> Gerando cores.json default a partir de $LIBRETRO_DIR"
    PS1_CORE="$LIBRETRO_DIR/mednafen_psx_libretro.so"
    SNES_CORE="$LIBRETRO_DIR/snes9x_libretro.so"
    {
        echo "{"
        first=1
        add_core() {
            local key="$1" path="$2"
            if [[ -f "$path" ]]; then
                [[ $first -eq 0 ]] && echo ","
                printf '  "%s": "%s"' "$key" "$path"
                first=0
            fi
        }
        add_core "ps1" "$PS1_CORE"
        add_core "snes" "$SNES_CORE"
        echo ""
        echo "}"
    } > "$CORES_JSON"
    echo "    cores.json gerado:"
    cat "$CORES_JSON"
else
    echo "==> cores.json já presente (montado ou de build anterior), mantendo."
fi

# ---------------------------------------------------------------------------
# 3. PulseAudio com null-sink (clock de áudio por software)
# ---------------------------------------------------------------------------
# Só quando audio_driver=pulse. Sobe um daemon PulseAudio de sistema com um
# único sink virtual (module-null-sink) — não toca em nenhum hardware, só
# fornece o clock de áudio que o RetroArch precisa para não rodar em fast
# forward. Funciona em WSL2 / qualquer container sem /dev/snd.
PULSE_PID=""
if [[ "$AUDIO_DRIVER" == "pulse" ]]; then
    echo "==> Subindo PulseAudio (null-sink) como clock de áudio"
    # Modo usuário (não --system, que tem ACL restritiva e dá 'Access denied'
    # no pactl). HOME/PULSE_RUNTIME_PATH graváveis permitem rodar como root.
    # -n ignora a config padrão e carrega só os módulos que precisamos.
    export HOME=/tmp PULSE_RUNTIME_PATH=/tmp/pulse XDG_RUNTIME_DIR=/tmp/xdg
    mkdir -p /tmp/pulse /tmp/xdg
    pulseaudio --exit-idle-time=-1 --disable-shm=true -n \
        -L "module-native-protocol-unix" \
        -L "module-null-sink sink_name=homegames sink_properties=device.description=HomeGames" \
        --daemonize=yes 2>/tmp/pulseaudio.log \
        || echo "    AVISO: PulseAudio não subiu (ver /tmp/pulseaudio.log)"
    sleep 1
    pactl set-default-sink homegames 2>/dev/null || true
    echo "    sinks: $(pactl list sinks short 2>/dev/null | awk '{print $2}' | tr '\n' ' ')"
fi

# ---------------------------------------------------------------------------
# 4. WebRTC host (acesso de outros dispositivos na LAN)
# ---------------------------------------------------------------------------
# Por padrão o mediamtx anuncia os IPs das interfaces do container (ex:
# 172.17.0.2), inalcançáveis por um celular na LAN — resultando em tela preta
# no WebRTC. Se HOMEGAMES_WEBRTC_HOST estiver setado (IP do host na LAN),
# injetamos em webrtcAdditionalHosts para o mediamtx anunciar um IP roteável.
MEDIAMTX_CONFIG="$APP_ROOT/config/mediamtx.yml"
if [[ -n "${HOMEGAMES_WEBRTC_HOST:-}" ]]; then
    echo "==> Configurando WebRTC para anunciar host $HOMEGAMES_WEBRTC_HOST"
    MEDIAMTX_CONFIG=/tmp/mediamtx.yml
    sed "s/^webrtcAdditionalHosts:.*/webrtcAdditionalHosts: [$HOMEGAMES_WEBRTC_HOST]/" \
        "$APP_ROOT/config/mediamtx.yml" > "$MEDIAMTX_CONFIG"
fi

# ---------------------------------------------------------------------------
# 5. Supervisor: mediamtx (background) + uvicorn (foreground)
# ---------------------------------------------------------------------------
MEDIAMTX_PID=""

cleanup() {
    echo "==> Encerrando (sinal recebido)..."
    if [[ -n "$MEDIAMTX_PID" ]] && kill -0 "$MEDIAMTX_PID" 2>/dev/null; then
        kill "$MEDIAMTX_PID" 2>/dev/null || true
        wait "$MEDIAMTX_PID" 2>/dev/null || true
    fi
    [[ -n "$PULSE_PID" ]] && kill "$PULSE_PID" 2>/dev/null || true
    pulseaudio --kill 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "==> Subindo mediamtx"
"$APP_ROOT/bin/mediamtx" "$MEDIAMTX_CONFIG" &
MEDIAMTX_PID=$!

# Pequena espera para o mediamtx abrir as portas antes do backend (que consulta
# a API dele em 9997 ao iniciar um jogo). Não é crítico — o _wait_stream_ready()
# do player já tem polling com timeout — mas evita ruído nos logs iniciais.
sleep 1

cd "$APP_ROOT/backend"

# Remonta o CIFS se o storage estava configurado para rede (storage.json e
# credenciais persistem em /data; o mount em si não sobrevive ao restart).
echo "==> Verificando storage de rede (remontar se mode=cifs)"
python -c "from app.services.storage import remount_if_configured; remount_if_configured()" \
    && echo "    storage verificado" || echo "    AVISO: falha ao remontar storage (reconfigure pela UI se necessário)"

# Auto-detecção do encoder de vídeo (só quando HOMEGAMES_ENCODER=auto). Roda os
# encode-probes uma vez e mostra qual hardware será usado — ajuda o usuário a
# saber se a GPU foi detectada ou se caiu para CPU. O resultado é cacheado no
# processo; o uvicorn (mesmo modulo) reaproveita.
if [[ "${HOMEGAMES_ENCODER:-}" == "auto" ]]; then
    echo "==> Detectando encoder de vídeo (nvenc > qsv > vaapi > libx264)..."
    python -c "from app.streaming.encoder_detect import detect_encoder, describe_encoder; print('    Encoder:', describe_encoder(detect_encoder()))"
fi

echo "==> Subindo backend (uvicorn) em foreground"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
