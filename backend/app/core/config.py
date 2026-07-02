"""Configuração central do RetroHost.

Todos os caminhos derivam de PROJECT_ROOT, que por padrão assume o layout
padrão do Raspberry Pi (/home/YOUR_USER/retrohost). Pode ser sobrescrito pela
variável de ambiente HOMEGAMES_ROOT para permitir execução local (Windows/dev).
"""
from __future__ import annotations

import os
from pathlib import Path


def _default_root() -> Path:
    env_root = os.environ.get("HOMEGAMES_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> root
    return Path(__file__).resolve().parents[3]


class Settings:
    PROJECT_ROOT: Path = _default_root()

    BACKEND_DIR: Path = PROJECT_ROOT / "backend"
    FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
    EMULATOR_DIR: Path = PROJECT_ROOT / "emulator"
    ROMS_DIR: Path = EMULATOR_DIR / "roms"
    BIOS_DIR: Path = EMULATOR_DIR / "bios"
    CORES_DIR: Path = EMULATOR_DIR / "cores"
    SAVES_DIR: Path = EMULATOR_DIR / "saves"
    STATES_DIR: Path = EMULATOR_DIR / "states"
    CONFIG_DIR: Path = PROJECT_ROOT / "config"
    LOGS_DIR: Path = PROJECT_ROOT / "logs"

    CORES_CONFIG_FILE: Path = CONFIG_DIR / "cores.json"
    SETTINGS_CONFIG_FILE: Path = CONFIG_DIR / "settings.json"
    # storage.json: default em config/ (Pi). No container, HOMEGAMES_STORAGE_CONFIG
    # aponta para /data (volume) para sobreviver a restarts do container, e o
    # entrypoint remonta o CIFS no boot se mode=cifs. Ver storage.py / entrypoint.
    STORAGE_CONFIG_FILE: Path = Path(
        os.environ.get("HOMEGAMES_STORAGE_CONFIG", str(CONFIG_DIR / "storage.json"))
    )
    RECORDCONFIG_PATH: Path = CONFIG_DIR / "retroarch" / "record_raw_av.cfg"

    # System directory do RetroArch (onde ficam BIOS etc). Vazio = comportamento
    # padrão do Pi (RetroArch usa o seu próprio default). No container o
    # entrypoint exporta HOMEGAMES_SYSTEM_DIR e o driver copia a BIOS de PS1 para
    # lá no launch (o core Beetle PSX exige BIOS). Ver drivers/retroarch.py.
    SYSTEM_DIR: str = os.environ.get("HOMEGAMES_SYSTEM_DIR", "")

    # No container WSL2 não há udevd para criar /dev/input/eventN quando o uinput
    # registra o teclado virtual. =1 faz o UInputKeyboardProvider criar o node via
    # mknod (lendo major:minor do sysfs). No Pi fica 0 (udev do sistema já cria).
    MKNOD_INPUT: bool = os.environ.get("HOMEGAMES_MKNOD_INPUT", "0") == "1"

    # Provider de input: "uinput" (Pi, teclado virtual via udev) ou "sdl"
    # (container/WSL2, joystick virtual SDL2 dentro do RetroArch via LD_PRELOAD —
    # ver container/sdl_input_preload.c e app/input/sdl_gamepad.py).
    INPUT_PROVIDER: str = os.environ.get("HOMEGAMES_INPUT_PROVIDER", "uinput")
    INPUT_SOCK_PATH: str = os.environ.get("HOMEGAMES_INPUT_SOCK", "/tmp/homegames_input.sock")
    # Caminho do LD_PRELOAD do input SDL (vazio = não usar). No container o
    # entrypoint/Dockerfile aponta para o .so compilado; o RetroArchDriver
    # injeta no ambiente do RetroArch quando INPUT_PROVIDER=sdl.
    INPUT_SDL_PRELOAD: str = os.environ.get("HOMEGAMES_SDL_PRELOAD", "")

    # Storage de ROMs via rede (CIFS/Samba) - ver app/services/storage.py.
    # CIFS_CREDENTIALS_PATH: no container vai para /data (volume) via env, para o
    # entrypoint conseguir remontar no boot. No Pi, fica em /etc/samba (root-only).
    CIFS_CREDENTIALS_PATH: Path = Path(
        os.environ.get("HOMEGAMES_CIFS_CREDENTIALS", "/etc/samba/homegames-credentials")
    )
    CIFS_MOUNT_POINT: Path = Path("/mnt/homegames-roms")
    # Versão do protocolo SMB para o mount -t cifs. Default 3.0 (moderno, seguro,
    # funciona em kernels novos como o do WSL2). Kernels antigos/servidores que só
    # falam SMB1 podem precisar de 2.0/1.0 via HOMEGAMES_CIFS_VERS. O kernel WSL2
    # (6.6) rejeita vers=2.0 com mount error(22) para alguns servidores.
    CIFS_VERS: str = os.environ.get("HOMEGAMES_CIFS_VERS", "3.0")

    STREAMING_FIFO_PATH: Path = Path("/tmp/homegames_av.fifo")
    MEDIAMTX_RTSP_URL: str = "rtsp://127.0.0.1:8554/live"
    # Encoder de vídeo do ffmpeg. Default h264_v4l2m2m (encoder de hardware do
    # Raspberry Pi). O container x86 seta HOMEGAMES_ENCODER=auto, que auto-detecta
    # o melhor encoder disponível (nvenc > qsv > vaapi > libx264) — imagem
    # agnóstica de GPU. Um valor explícito força aquele encoder (override/debug).
    # Ver app/streaming/encoder_detect.py e encoder_profiles.py.
    VIDEO_ENCODER: str = os.environ.get("HOMEGAMES_ENCODER", "h264_v4l2m2m")
    # Render node DRM para VAAPI/QSV (GPU Intel/AMD). Default /dev/dri/renderD128;
    # máquinas com múltiplas GPUs podem precisar de renderD129 etc.
    RENDER_NODE: str = os.environ.get("HOMEGAMES_RENDER_NODE", "/dev/dri/renderD128")
    MEDIAMTX_WHEP_PORT: int = 8889
    MEDIAMTX_WHEP_PATH: str = "/live/whep"
    MEDIAMTX_API_URL: str = "http://127.0.0.1:9997/v3/paths/get/live"

    # Default: backend/homegames.db (layout do Pi). No container, HOMEGAMES_DB_PATH
    # aponta para um diretório de dados montado como volume, separado do código —
    # ver scripts/docker-entrypoint.sh / docker-run.sh.
    DATABASE_PATH: Path = Path(os.environ.get("HOMEGAMES_DB_PATH", str(BACKEND_DIR / "homegames.db")))
    DATABASE_URL: str = f"sqlite:///{DATABASE_PATH}"

    # Extensões de ROM válidas (jogo "jogável") por console.
    VALID_ROM_EXTENSIONS: dict[str, set[str]] = {
        "ps1": {".cue", ".chd", ".pbp"},
        "snes": {".sfc", ".smc"},
    }

    HOST: str = "0.0.0.0"
    PORT: int = 8000


settings = Settings()
