# HomeGames — imagem containerizada AGNÓSTICA DE GPU para Linux x86_64.
#
# Replica o pipeline do Raspberry Pi (RetroArch headless -> FIFO -> ffmpeg ->
# mediamtx -> WebRTC + input + FastAPI), mas a MESMA imagem roda em qualquer
# máquina: NVIDIA, Intel (QuickSync), AMD/Intel (VAAPI) ou só CPU (libx264).
# O encoder é auto-detectado no boot (HOMEGAMES_ENCODER=auto -> nvenc > qsv >
# vaapi > libx264). Ver ARCHITECTURE.md (seção "Modo container").
#
# Base ubuntu:24.04 (genérica, leve). Para NVENC, o nvidia-container-toolkit
# injeta libnvidia-encode do host em runtime quando se passa `--gpus all` — não
# precisa da base CUDA. Para Intel/AMD, passar `--device /dev/dri`. Sem nenhuma
# flag de GPU, a auto-detecção cai para libx264 (CPU) e sobe em qualquer lugar.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Dicas para o nvidia-container-toolkit quando ELE estiver presente (--gpus all):
# 'all' inclui as capabilities de vídeo (sem elas o libnvidia-encode.so.1 não é
# montado e o NVENC falha). Inócuo quando não há GPU NVIDIA/toolkit.
ENV NVIDIA_DRIVER_CAPABILITIES=all \
    NVIDIA_VISIBLE_DEVICES=all

# - retroarch + cores libretro (PS1 via beetle-psx/mednafen; SNES via snes9x).
#   No Ubuntu 24.04 não há pacote pcsx-rearmed; libretro-beetle-psx instala o
#   core mednafen_psx_libretro.so (Beetle PSX), inclusive mais preciso.
#   PCSX2 (PS2) NÃO entra aqui ainda — ver ARCHITECTURE.md (precisa de GL/Vulkan
#   real, video_driver=null não basta). cores.json mapeia console->core, então
#   adicionar PS2 depois é configuração + instalar o core.
# - ffmpeg: o do Ubuntu 24.04 traz TODOS os encoders H.264 (libx264, h264_nvenc,
#   h264_qsv, h264_vaapi) — uma imagem cobre todo hardware. Auto-detecção escolhe.
# - libva2/libva-drm2/intel-media-va-driver-non-free/mesa-va-drivers/vainfo:
#   runtime VAAPI/QSV (Intel QuickSync e AMD/Intel via Mesa). Ficam dormentes se
#   /dev/dri não for passado; habilitam encode por GPU Intel/AMD quando passado.
#   (NVENC não precisa destes — vem do host via nvidia-container-toolkit.)
# - python3-evdev: input via uinput no Pi (no container usamos SDL, mas mantido
#   para o provider uinput continuar importável).
# - cifs-utils: storage de ROMs via rede (CIFS/Samba).
# - pulseaudio: clock de áudio dummy (null-sink) DENTRO do container — sem ele o
#   RetroArch roda em "fast forward" (audio_sync precisa de clock). Ver entrypoint.
RUN apt-get update && apt-get install -y --no-install-recommends \
        retroarch \
        libretro-beetle-psx \
        libretro-snes9x \
        ffmpeg \
        libva2 \
        libva-drm2 \
        intel-media-va-driver-non-free \
        mesa-va-drivers \
        vainfo \
        pulseaudio \
        pulseaudio-utils \
        python3 \
        python3-venv \
        python3-pip \
        python3-evdev \
        cifs-utils \
        sudo \
        procps \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# O storage CIFS (app/services/storage.py) chama `sudo mount/umount/tee` — no Pi
# isso é restrito por uma regra sudoers de escopo mínimo. No container o processo
# já roda como root, então `sudo` apenas repassa o comando (sem senha). Instalar
# o pacote sudo evita FileNotFoundError sem precisar de lógica de ambiente no
# código. O mount -t cifs em si exige --privileged no docker run.

# Esta imagem é x86_64 (amd64) ONLY: o mediamtx é baixado como linux_amd64 e os
# cores libretro vêm do apt da arch do build. Falha cedo com mensagem clara se
# alguém buildar em ARM (ex: Mac M1+) em vez de quebrar de forma confusa depois.
# Suporte ARM seria possível (baixar mediamtx por arch via TARGETARCH do buildx)
# mas não foi validado — ver SECURITY.md / ARCHITECTURE.md.
RUN arch="$(uname -m)"; \
    if [ "$arch" != "x86_64" ]; then \
        echo "ERRO: HomeGames container é x86_64-only; arquitetura detectada: $arch." >&2; \
        echo "Builde numa máquina/plataforma amd64 (ou use --platform linux/amd64)." >&2; \
        exit 1; \
    fi

# mediamtx (não distribuído via apt) — release oficial do GitHub, build amd64.
# Mesma versão usada no Pi (scripts/install_mediamtx.sh, lá com asset armv7).
ARG MEDIAMTX_VERSION=v1.19.2
# SHA-256 do asset linux_amd64 para v1.19.2 — atualizar ao trocar MEDIAMTX_VERSION.
ARG MEDIAMTX_SHA256=f9c601cc303ceca8fad2883917b022882672c5bc56311e92dbceb16e5f20c60c
RUN mkdir -p /app/bin \
    && curl -sL -o /tmp/mediamtx.tar.gz \
        "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/mediamtx_${MEDIAMTX_VERSION}_linux_amd64.tar.gz" \
    && echo "${MEDIAMTX_SHA256}  /tmp/mediamtx.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/mediamtx.tar.gz -C /app/bin mediamtx \
    && chmod +x /app/bin/mediamtx \
    && rm /tmp/mediamtx.tar.gz

WORKDIR /app

# Código do projeto (backend, frontend, config, scripts, container). O
# .dockerignore exclui .venv/, bin/ local, *.db, roms, __pycache__, .git.
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY config/ /app/config/
COPY scripts/ /app/scripts/
COPY container/ /app/container/

# venv com --system-site-packages para enxergar o python3-evdev do apt (idêntico
# ao que o setup_input.sh faz no Pi).
RUN python3 -m venv --system-site-packages /app/backend/.venv \
    && /app/backend/.venv/bin/pip install --no-cache-dir -r /app/backend/requirements.txt

# Compila o LD_PRELOAD do input SDL (joystick virtual dentro do RetroArch — ver
# container/sdl_input_preload.c). gcc é instalado só para o build e removido.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libsdl2-dev \
    && gcc -shared -fPIC -o /app/container/sdl_input_preload.so \
        /app/container/sdl_input_preload.c -ldl -lpthread \
    && apt-get purge -y gcc libc6-dev libsdl2-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN chmod +x /app/scripts/docker-entrypoint.sh

# /data: dados persistentes (SQLite), separado do código para montar como volume.
# /mnt/homegames-roms: ponto de montagem do storage CIFS.
# /etc/samba: onde vai o arquivo de credenciais CIFS (CIFS_CREDENTIALS_PATH).
# No Pi tudo isso é criado pelo setup_network_storage.sh; no container, aqui.
RUN mkdir -p /data /mnt/homegames-roms /etc/samba

# HOMEGAMES_ROOT: faz core/config.py resolver todos os paths a partir de /app.
# HOMEGAMES_ENCODER=auto: auto-detecta o encoder (nvenc>qsv>vaapi>libx264) —
# imagem agnóstica de GPU.
# HOMEGAMES_DB_PATH / STORAGE_CONFIG / CIFS_CREDENTIALS: tudo em /data (volume),
# para o banco, a config de storage e as credenciais CIFS sobreviverem a
# restarts e o entrypoint conseguir remontar o CIFS no boot.
ENV HOMEGAMES_ROOT=/app \
    HOMEGAMES_ENCODER=auto \
    HOMEGAMES_DB_PATH=/data/homegames.db \
    HOMEGAMES_STORAGE_CONFIG=/data/storage.json \
    HOMEGAMES_CIFS_CREDENTIALS=/data/homegames-credentials \
    HOMEGAMES_INPUT_PROVIDER=sdl \
    HOMEGAMES_SDL_PRELOAD=/app/container/sdl_input_preload.so \
    PATH=/app/backend/.venv/bin:$PATH

# 8000 FastAPI/WHEP signaling, 8889 WHEP, 8189/udp ICE (WebRTC), 8554 RTSP interno.
EXPOSE 8000 8889 8554 8189/udp

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
