"""Tests for the ROM scanner (scanner.py).

Uses an in-memory SQLite database and a temporary directory tree —
no filesystem side effects, no real ROMs needed.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.models.game import Game
from app.services.scanner import scan_roms


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def make_rom_tree(base: "Path", structure: dict) -> None:
    """Helper: build a directory tree from a dict of {relative_path: content}."""
    from pathlib import Path
    for rel_path, content in structure.items():
        full = base / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content or "")


# ---------------------------------------------------------------------------
# Basic scanning
# ---------------------------------------------------------------------------

class TestScanRoms:
    def test_finds_valid_ps1_cue(self, db, tmp_path):
        make_rom_tree(tmp_path, {
            "ps1/Crash Bandicoot/Crash Bandicoot.cue": "",
            "ps1/Crash Bandicoot/Crash Bandicoot.bin": "",
        })
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 1
        assert result["added"] == 1
        assert result["games"][0].title == "Crash Bandicoot"
        assert result["games"][0].console == "ps1"

    def test_finds_valid_snes_rom(self, db, tmp_path):
        make_rom_tree(tmp_path, {"snes/Super Mario World/Super Mario World.sfc": ""})
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 1
        assert result["games"][0].console == "snes"

    def test_empty_roms_dir_returns_zero(self, db, tmp_path):
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 0
        assert result["added"] == 0

    def test_nonexistent_roms_dir_returns_zero(self, db, tmp_path):
        result = scan_roms(db, roms_dir=tmp_path / "does_not_exist")
        assert result["scanned"] == 0

    def test_unknown_console_dir_is_skipped(self, db, tmp_path):
        make_rom_tree(tmp_path, {"n64/Zelda/Zelda.z64": ""})
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 0

    def test_auxiliary_bin_files_are_not_listed(self, db, tmp_path):
        make_rom_tree(tmp_path, {
            "ps1/Crash 2/Crash 2.cue": "",
            "ps1/Crash 2/Crash 2.bin": "",
            "ps1/Crash 2/Crash 2 (Track 2).bin": "",
        })
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 1  # only the .cue

    def test_chd_is_valid_ps1_format(self, db, tmp_path):
        make_rom_tree(tmp_path, {"ps1/Dino Crisis/Dino Crisis.chd": ""})
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 1


# ---------------------------------------------------------------------------
# Hidden files (.homegames_*.cue artifacts) are ignored
# ---------------------------------------------------------------------------

class TestHiddenFileFilter:
    def test_dot_prefixed_cue_is_ignored(self, db, tmp_path):
        make_rom_tree(tmp_path, {
            "ps1/Crash 2/Crash 2.cue": "",
            "ps1/Crash 2/.homegames_Crash 2.cue": "",
            "ps1/Crash 2/Crash 2.bin": "",
        })
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 1
        assert result["games"][0].title == "Crash 2"

    def test_only_hidden_file_yields_zero(self, db, tmp_path):
        make_rom_tree(tmp_path, {
            "ps1/Game/.homegames_Game.cue": "",
        })
        result = scan_roms(db, roms_dir=tmp_path)
        assert result["scanned"] == 0


# ---------------------------------------------------------------------------
# Upsert behaviour
# ---------------------------------------------------------------------------

class TestUpsert:
    def test_second_scan_updates_not_adds(self, db, tmp_path):
        make_rom_tree(tmp_path, {"ps1/Game/Game.cue": ""})
        scan_roms(db, roms_dir=tmp_path)
        result2 = scan_roms(db, roms_dir=tmp_path)
        assert result2["added"] == 0
        assert result2["updated"] == 1
        assert db.query(Game).count() == 1

    def test_new_game_after_first_scan_is_added(self, db, tmp_path):
        make_rom_tree(tmp_path, {"ps1/Game1/Game1.cue": ""})
        scan_roms(db, roms_dir=tmp_path)

        make_rom_tree(tmp_path, {"ps1/Game2/Game2.cue": ""})
        result2 = scan_roms(db, roms_dir=tmp_path)
        assert result2["added"] == 1
        assert db.query(Game).count() == 2
