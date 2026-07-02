#!/usr/bin/env bash
# Configura o Raspberry Pi para rodar RetroArch headless (sem TV/monitor físico)
# e expor video raw via FIFO para captura externa por ffmpeg.
#
# Idempotente: pode ser executado mais de uma vez sem duplicar configuração.
# Requer reboot manual depois de alterar /boot/firmware/config.txt na primeira vez.
set -euo pipefail

BOOT_CONFIG="/boot/firmware/config.txt"
RETROARCH_CFG="$HOME/.config/retroarch/retroarch.cfg"

echo "==> Configurando $BOOT_CONFIG (hotplug HDMI forçado para renderização offscreen)"
if ! grep -q "^hdmi_force_hotplug=1" "$BOOT_CONFIG"; then
    sudo cp "$BOOT_CONFIG" "${BOOT_CONFIG}.bak.$(date +%s)"
    sudo tee -a "$BOOT_CONFIG" > /dev/null <<'EOF'

# RetroHost: forca deteccao de display mesmo sem TV/monitor conectado fisicamente
# (necessario para RetroArch renderizar offscreen para captura/streaming headless)
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=85
EOF
    echo "    Adicionado. REBOOT NECESSARIO (sudo reboot) antes de testar streaming."
else
    echo "    Já configurado, nada a fazer."
fi

echo "==> Configurando $RETROARCH_CFG"
if [[ ! -f "$RETROARCH_CFG" ]]; then
    echo "    Arquivo não existe ainda. Rode 'retroarch' uma vez (mesmo que falhe) para gerá-lo, depois rode este script de novo."
    exit 1
fi

set_cfg_key() {
    local key="$1"
    local value="$2"
    if grep -qE "^${key} = " "$RETROARCH_CFG"; then
        sed -i "s/^${key} = .*/${key} = \"${value}\"/" "$RETROARCH_CFG"
    else
        echo "${key} = \"${value}\"" >> "$RETROARCH_CFG"
    fi
    echo "    ${key} = \"${value}\""
}

# video_driver=null: RetroArch não precisa de display físico nem GPU/shader
#   compatível — o jogo é capturado via record/FIFO, não exibido localmente.
# input_driver=udev: não depende de X11/Wayland (o driver "x" exige sessão gráfica).
# audio_driver=alsa: PulseAudio não roda neste setup headless; ALSA acessa
#   /dev/snd direto. Sem áudio funcionando, audio_sync não consegue limitar o
#   ritmo do core e o jogo roda em "fast forward" (bug observado e corrigido).
set_cfg_key "video_driver" "null"
set_cfg_key "video_context_driver" ""
set_cfg_key "video_shader_enable" "false"
set_cfg_key "input_driver" "udev"
set_cfg_key "audio_driver" "alsa"

echo "==> Concluído."
