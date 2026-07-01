"""Configura de onde o HomeGames lê ROMs: disco local (padrão) ou um share
de rede CIFS/Samba montado sob demanda no sistema operacional do Pi.

RetroArchDriver/PlayerService não sabem nem precisam saber qual modo está
ativo - eles só recebem game.launch_file, um path de arquivo comum. Quem
decide qual diretório escanear é effective_roms_dir(), usado pelo scanner.

Montar/desmontar exige privilégio elevado (mount -t cifs). O backend roda
`sudo mount`/`sudo umount` restrito por uma regra sudoers de escopo mínimo
(ver config/sudoers/homegames-mount, instalada via scripts/setup_network_storage.sh)
- não há sudo livre dentro do processo do serviço.
"""
import json
import subprocess
from pathlib import Path

from app.core.config import settings


class StorageConfigError(RuntimeError):
    pass


def get_storage_config() -> dict:
    if not settings.STORAGE_CONFIG_FILE.exists():
        return {"mode": "local", "cifs_host": None, "cifs_share": None, "cifs_username": None, "cifs_subpath": None}
    with open(settings.STORAGE_CONFIG_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def _write_storage_config(config: dict) -> None:
    settings.STORAGE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.STORAGE_CONFIG_FILE, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)


def _is_mounted() -> bool:
    try:
        result = subprocess.run(
            ["mountpoint", "-q", str(settings.CIFS_MOUNT_POINT)],
            check=False,
        )
    except OSError:
        # "mountpoint" não existe neste SO (ex: dev local no Windows) - só o
        # Pi real monta CIFS de fato, então tratamos como "não montado".
        return False
    return result.returncode == 0


def _unmount_if_needed() -> None:
    if not _is_mounted():
        return
    try:
        subprocess.run(
            ["sudo", "umount", str(settings.CIFS_MOUNT_POINT)],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise StorageConfigError(f"Comando de desmontagem indisponível neste sistema: {exc}") from exc


def set_local_storage() -> None:
    try:
        _unmount_if_needed()
    except subprocess.CalledProcessError as exc:
        raise StorageConfigError(f"Falha ao desmontar o storage de rede: {exc.stderr}") from exc
    _write_storage_config(
        {"mode": "local", "cifs_host": None, "cifs_share": None, "cifs_username": None, "cifs_subpath": None}
    )


def set_cifs_storage(host: str, share: str, username: str, password: str, subpath: str = "") -> None:
    try:
        _unmount_if_needed()
    except subprocess.CalledProcessError as exc:
        raise StorageConfigError(f"Falha ao desmontar montagem anterior: {exc.stderr}") from exc

    credentials_content = f"username={username}\npassword={password}\n"
    try:
        subprocess.run(
            ["sudo", "tee", str(settings.CIFS_CREDENTIALS_PATH)],
            input=credentials_content,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(["sudo", "chmod", "600", str(settings.CIFS_CREDENTIALS_PATH)], check=True)
    except subprocess.CalledProcessError as exc:
        raise StorageConfigError(f"Falha ao gravar credenciais: {exc.stderr}") from exc
    except OSError as exc:
        raise StorageConfigError(f"Comando de montagem indisponível neste sistema: {exc}") from exc

    mount_command = [
        "sudo", "mount", "-t", "cifs",
        f"//{host}/{share}", str(settings.CIFS_MOUNT_POINT),
        "-o", f"credentials={settings.CIFS_CREDENTIALS_PATH},uid=1000,gid=1000,vers={settings.CIFS_VERS}",
    ]
    try:
        subprocess.run(mount_command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise StorageConfigError(f"Falha ao montar //{host}/{share}: {exc.stderr}") from exc
    except OSError as exc:
        raise StorageConfigError(f"Comando de montagem indisponível neste sistema: {exc}") from exc

    _write_storage_config(
        {
            "mode": "cifs",
            "cifs_host": host,
            "cifs_share": share,
            "cifs_username": username,
            "cifs_subpath": subpath or None,
        }
    )


def _mount_from_config(config: dict) -> None:
    """Monta o CIFS a partir de uma config de storage. Levanta StorageConfigError
    com mensagem clara em caso de falha. Pressupõe credenciais já gravadas."""
    host, share = config.get("cifs_host"), config.get("cifs_share")
    mount_command = [
        "sudo", "mount", "-t", "cifs",
        f"//{host}/{share}", str(settings.CIFS_MOUNT_POINT),
        "-o", f"credentials={settings.CIFS_CREDENTIALS_PATH},uid=1000,gid=1000,vers={settings.CIFS_VERS}",
    ]
    try:
        subprocess.run(mount_command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise StorageConfigError(f"Falha ao montar //{host}/{share}: {exc.stderr}") from exc
    except OSError as exc:
        raise StorageConfigError(f"Comando de montagem indisponível: {exc}") from exc


def _can_remount() -> bool:
    """True se o storage está configurado p/ CIFS, não montado e remontável."""
    config = get_storage_config()
    return (
        config.get("mode") == "cifs"
        and not _is_mounted()
        and settings.CIFS_CREDENTIALS_PATH.exists()
        and bool(config.get("cifs_host"))
        and bool(config.get("cifs_share"))
    )


def remount_if_configured() -> None:
    """Remonta o CIFS no boot do container se configurado p/ rede (silencioso).

    O mount CIFS vive no namespace do container e NÃO sobrevive a restart. storage.json
    e credenciais persistem em volume; isto remonta sem o usuário reconfigurar.
    Falha silenciosa: não derruba o boot do backend se o servidor estiver offline.
    """
    if not _can_remount():
        return
    try:
        _mount_from_config(get_storage_config())
    except StorageConfigError:
        return


def ensure_storage_mounted() -> None:
    """Garante o CIFS montado antes de iniciar um jogo (on-demand).

    O mount pode cair durante o uso (Wi-Fi, timeout de inatividade). Chamado pelo
    PlayerService.play(); se o storage é CIFS e caiu, remonta — e propaga
    StorageConfigError (vira HTTP/erro na UI) se não conseguir, em vez de o jogo
    falhar com 'Failed to load content' sem explicação. No-op se local ou já montado.
    """
    if _can_remount():
        _mount_from_config(get_storage_config())


def effective_roms_dir() -> Path:
    config = get_storage_config()
    if config["mode"] == "cifs":
        subpath = config.get("cifs_subpath")
        if subpath:
            return settings.CIFS_MOUNT_POINT / subpath
        return settings.CIFS_MOUNT_POINT
    return settings.ROMS_DIR
