"""Scanner de biblioteca de ROMs.

Percorre emulator/roms/<console>/, identifica jogos válidos por extensão
(ignorando arquivos auxiliares como .bin/.ccd/.sub/.ecm) e faz upsert no
SQLite. Um jogo é identificado pelo seu launch_file (.cue/.chd/.pbp);
arquivos auxiliares na mesma pasta nunca são listados como jogo.
"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.game import Game
from app.services.storage import effective_roms_dir


def clear_games(db: Session) -> None:
    db.query(Game).delete()
    db.commit()


def scan_roms(db: Session, roms_dir: Path | None = None) -> dict:
    roms_dir = roms_dir or effective_roms_dir()
    found_launch_files: list[tuple[str, str, Path]] = []  # (console, title, launch_file)

    if roms_dir.exists():
        for console_dir in sorted(p for p in roms_dir.iterdir() if p.is_dir()):
            console = console_dir.name
            valid_extensions = settings.VALID_ROM_EXTENSIONS.get(console)
            if not valid_extensions:
                continue
            for launch_file in sorted(console_dir.rglob("*")):
                if not launch_file.is_file():
                    continue
                if launch_file.suffix.lower() not in valid_extensions:
                    continue
                # Ignora arquivos ocultos (prefixo ponto), incluindo os
                # .homegames_*.cue gerados pelo RetroArchDriver ao corrigir um
                # .cue quebrado — não são jogos, são artefatos de runtime.
                if launch_file.name.startswith("."):
                    continue
                title = launch_file.stem
                found_launch_files.append((console, title, launch_file))

    found_paths = {str(lf) for _, _, lf in found_launch_files}

    # Remove registros cujos arquivos não existem mais no storage.
    removed = 0
    for game in db.query(Game).all():
        if game.launch_file not in found_paths:
            db.delete(game)
            removed += 1

    added = 0
    updated = 0
    for console, title, launch_file in found_launch_files:
        existing = db.query(Game).filter(Game.launch_file == str(launch_file)).one_or_none()
        if existing is None:
            db.add(
                Game(
                    console=console,
                    title=title,
                    path=str(launch_file.parent),
                    launch_file=str(launch_file),
                )
            )
            added += 1
        else:
            existing.title = title
            existing.path = str(launch_file.parent)
            updated += 1

    db.commit()

    all_games = db.query(Game).order_by(Game.title).all()
    return {
        "scanned": len(found_launch_files),
        "added": added,
        "updated": updated,
        "removed": removed,
        "games": all_games,
    }
