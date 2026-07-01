"""Driver concreto que executa jogos via RetroArch (subprocess).

O mapeamento console -> core libretro é lido de config/cores.json. Se o core
configurado para o console do jogo não existir no disco, levantamos
CoreNotConfiguredError em vez de tentar executar — o serviço de player traduz
isso para uma resposta HTTP amigável.

RetroArch sempre roda headless (sem HDMI/display físico): grava vídeo raw +
áudio PCM num named pipe (FIFO) via --recordconfig, que o FFmpegStreamingProvider
lê do outro lado para codificar e publicar via WebRTC. video_driver=null,
input_driver=udev e audio_driver=alsa precisam estar configurados em
retroarch.cfg no Pi (ver scripts/setup_streaming.sh) — sem isso o RetroArch
falha ao inicializar ou roda em "fast forward" (audio_sync sem áudio real).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.drivers.base import CoreNotConfiguredError, EmulatorDriver

# Nomes de BIOS de PS1 que o core Beetle PSX procura (JP/US/EU). Copiamos a BIOS
# encontrada no storage com os três nomes para cobrir qualquer região da ROM.
_PS1_BIOS_NAMES = ("scph5500.bin", "scph5501.bin", "scph5502.bin")


class RetroArchDriver(EmulatorDriver):
    def __init__(self, retroarch_bin: str = "retroarch") -> None:
        self.retroarch_bin = retroarch_bin
        self._process: subprocess.Popen | None = None

    def _load_core_map(self) -> dict[str, str]:
        if not settings.CORES_CONFIG_FILE.exists():
            return {}
        with open(settings.CORES_CONFIG_FILE, encoding="utf-8") as fh:
            return json.load(fh)

    def _resolve_core(self, console: str) -> Path:
        core_map = self._load_core_map()
        core_path = core_map.get(console)
        if not core_path or not Path(core_path).is_file():
            raise CoreNotConfiguredError(
                f"Core para o console '{console}' ainda não foi configurado. "
                f"Adicione o caminho do core .so em {settings.CORES_CONFIG_FILE} "
                f"e coloque o arquivo em {settings.CORES_DIR}."
            )
        return Path(core_path)

    def _ensure_ps1_bios(self, game: Any) -> None:
        """Copia a BIOS de PS1 do storage para o SYSTEM_DIR, se necessário.

        O core Beetle PSX (usado no container x86) exige a BIOS — diferente do
        pcsx-rearmed do Pi, que tem HLE BIOS. Procuramos um scph*.bin no mesmo
        storage das ROMs (effective_roms_dir) e copiamos com os nomes que o core
        espera. No-op se SYSTEM_DIR não está configurado (ex: no Pi) ou se a BIOS
        já está lá. Falhas aqui não levantam — o RetroArch dará o erro claro.
        """
        if not settings.SYSTEM_DIR or game.console != "ps1":
            return
        system_dir = Path(settings.SYSTEM_DIR)
        if (system_dir / _PS1_BIOS_NAMES[1]).exists():
            return  # já copiada
        from app.services.storage import effective_roms_dir

        try:
            bios_src = next(effective_roms_dir().rglob("[Ss][Cc][Pp][Hh]*.[Bb][Ii][Nn]"), None)
            if bios_src is None:
                return
            system_dir.mkdir(parents=True, exist_ok=True)
            for name in _PS1_BIOS_NAMES:
                shutil.copy(bios_src, system_dir / name)
        except OSError:
            return

    def _resolve_launch_file(self, launch_file: str) -> str:
        """Conserta .cue com referências FILE quebradas (path absoluto Windows).

        ROMs dumpadas em PCs Windows (ePSXe etc.) gravam no .cue caminhos como
        FILE "C:\\CRASH 2.BIN" ou um path absoluto inteiro — que não existem no
        Linux. Se a referência não existir mas houver um arquivo de mesmo nome-
        base (ou um único .bin/.iso) ao lado do .cue, geramos um .cue corrigido
        num tmp apontando para o arquivo real (sem alterar o original no storage).
        Retorna o caminho a usar (o tmp corrigido, ou o original se estiver ok).
        """
        path = Path(launch_file)
        if path.suffix.lower() != ".cue":
            return launch_file
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            return launch_file

        game_dir = path.parent
        changed = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith("FILE "):
                # extrai o nome entre aspas
                start, end = line.find('"'), line.rfind('"')
                if start != -1 and end > start:
                    ref = line[start + 1:end]
                    ref_basename = ref.replace("\\", "/").rsplit("/", 1)[-1]
                    # Corrige se: (a) a ref tem path embutido (Windows "C:\..." ou
                    # absoluto "/..."), que o core tentaria abrir literalmente, ou
                    # (b) nem o basename existe ao lado do .cue. Caso contrário,
                    # mantém (ref já é um nome relativo válido, como no Tarzan).
                    has_path = ("\\" in ref) or (":" in ref) or ("/" in ref)
                    if has_path or not (game_dir / ref_basename).is_file():
                        replacement = self._find_track_file(game_dir, ref_basename)
                        if replacement is not None:
                            line = line[:start + 1] + replacement + line[end:]
                            changed = True
            new_lines.append(line)

        if not changed:
            return launch_file
        # O .cue corrigido PRECISA ficar no mesmo diretório dos arquivos de faixa:
        # o core (Mednafen/Beetle PSX) resolve a linha FILE relativa ao diretório
        # do .cue, não ao cwd. Gravamos um .cue irmão com prefixo. Se o diretório
        # for read-only, caímos de volta no original (o core dará o erro claro).
        fixed_cue = path.with_name(f".homegames_{path.name}")
        try:
            fixed_cue.write_text("\n".join(new_lines) + "\n")
        except OSError:
            return launch_file
        return str(fixed_cue)

    @staticmethod
    def _find_track_file(game_dir: Path, ref_basename: str) -> str | None:
        """Acha o arquivo de faixa real para uma referência FILE quebrada."""
        stem = Path(ref_basename).stem
        # 1) mesmo nome-base, qualquer extensão de imagem de disco
        for ext in (".bin", ".iso", ".img"):
            for candidate in game_dir.glob("*"):
                if candidate.stem.lower() == stem.lower() and candidate.suffix.lower() == ext:
                    return candidate.name
        # 2) fallback: se há um único .bin/.iso na pasta, usa ele
        images = [p for p in game_dir.iterdir()
                  if p.suffix.lower() in (".bin", ".iso", ".img")]
        if len(images) == 1:
            return images[0].name
        return None

    def launch(self, game: Any) -> None:
        if self.status():
            raise RuntimeError("Já existe um jogo em execução. Pare-o antes de iniciar outro.")

        core_path = self._resolve_core(game.console)
        self._ensure_ps1_bios(game)
        launch_file = self._resolve_launch_file(game.launch_file)

        fifo_path = settings.STREAMING_FIFO_PATH
        if fifo_path.exists():
            os.remove(fifo_path)
        os.mkfifo(fifo_path)

        command = [
            self.retroarch_bin, "-f",
            "-r", str(fifo_path),
            "--recordconfig", str(settings.RECORDCONFIG_PATH),
            "-L", str(core_path),
            launch_file,
        ]
        # cwd = diretório do jogo: cores baseados em .cue (ex: Beetle PSX)
        # resolvem os arquivos de faixa (.bin) relativos ao cwd, não ao .cue.
        # Sem isso, "Failed to load content" ao rodar de outro diretório.
        launch_dir = Path(game.launch_file).parent
        cwd = str(launch_dir) if launch_dir.is_dir() else None
        self._process = subprocess.Popen(command, cwd=cwd, env=self._launch_env())

    def _launch_env(self) -> dict[str, str] | None:
        """Ambiente do RetroArch. No modo de input SDL (container), injeta o
        LD_PRELOAD do joystick virtual e força SDL a não abrir vídeo/áudio real."""
        if settings.INPUT_PROVIDER != "sdl" or not settings.INPUT_SDL_PRELOAD:
            return None
        env = dict(os.environ)
        preload = settings.INPUT_SDL_PRELOAD
        if env.get("LD_PRELOAD"):
            preload = f"{env['LD_PRELOAD']}:{preload}"
        env["LD_PRELOAD"] = preload
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        env.setdefault("SDL_AUDIODRIVER", "dummy")
        env["HOMEGAMES_INPUT_SOCK"] = settings.INPUT_SOCK_PATH
        return env

    def stop(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        self._process = None

        fifo_path = settings.STREAMING_FIFO_PATH
        if fifo_path.exists():
            os.remove(fifo_path)

    def status(self) -> bool:
        if self._process is None:
            return False
        if self._process.poll() is None:
            return True
        self._process = None
        return False
