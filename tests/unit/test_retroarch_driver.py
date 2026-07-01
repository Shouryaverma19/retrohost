"""Tests for RetroArchDriver helpers (retroarch.py).

Tests cover _resolve_launch_file (Windows .cue path fixing) and
_find_track_file (track file resolution). No subprocess is spawned.
"""
import pytest

from app.drivers.retroarch import RetroArchDriver


@pytest.fixture()
def driver() -> RetroArchDriver:
    return RetroArchDriver()


# ---------------------------------------------------------------------------
# _find_track_file
# ---------------------------------------------------------------------------

class TestFindTrackFile:
    def test_finds_by_exact_stem(self, tmp_path):
        bin_file = tmp_path / "Crash Bandicoot.bin"
        bin_file.touch()
        result = RetroArchDriver._find_track_file(tmp_path, "Crash Bandicoot.bin")
        assert result == "Crash Bandicoot.bin"

    def test_finds_case_insensitive(self, tmp_path):
        bin_file = tmp_path / "CRASH.BIN"
        bin_file.touch()
        result = RetroArchDriver._find_track_file(tmp_path, "crash.bin")
        assert result == "CRASH.BIN"

    def test_fallback_to_single_bin(self, tmp_path):
        only_bin = tmp_path / "game.bin"
        only_bin.touch()
        # ref_basename doesn't match but there's only one .bin
        result = RetroArchDriver._find_track_file(tmp_path, "something_else.bin")
        assert result == "game.bin"

    def test_returns_none_when_ambiguous(self, tmp_path):
        (tmp_path / "track1.bin").touch()
        (tmp_path / "track2.bin").touch()
        result = RetroArchDriver._find_track_file(tmp_path, "nonexistent.bin")
        assert result is None

    def test_returns_none_when_no_images(self, tmp_path):
        (tmp_path / "readme.txt").touch()
        result = RetroArchDriver._find_track_file(tmp_path, "game.bin")
        assert result is None

    def test_finds_iso_extension(self, tmp_path):
        iso_file = tmp_path / "game.iso"
        iso_file.touch()
        result = RetroArchDriver._find_track_file(tmp_path, "game.iso")
        assert result == "game.iso"


# ---------------------------------------------------------------------------
# _resolve_launch_file
# ---------------------------------------------------------------------------

class TestResolveLaunchFile:
    def test_non_cue_file_is_returned_unchanged(self, driver, tmp_path):
        chd = tmp_path / "game.chd"
        chd.touch()
        assert driver._resolve_launch_file(str(chd)) == str(chd)

    def test_valid_relative_cue_is_returned_unchanged(self, driver, tmp_path):
        """A .cue with a valid relative FILE reference needs no fixing."""
        bin_file = tmp_path / "Tarzan.bin"
        bin_file.touch()
        cue = tmp_path / "Tarzan.cue"
        cue.write_text('FILE "Tarzan.bin" BINARY\n  TRACK 01 MODE2/2352\n')
        result = driver._resolve_launch_file(str(cue))
        assert result == str(cue)

    def test_windows_absolute_path_is_fixed(self, driver, tmp_path):
        """FILE "C:\\CRASH 2.BIN" must be rewritten to the local filename."""
        bin_file = tmp_path / "CRASH 2.BIN"
        bin_file.touch()
        cue = tmp_path / "Crash2.cue"
        cue.write_text('FILE "C:\\CRASH 2.BIN" BINARY\n  TRACK 01 MODE2/2352\n')

        result = driver._resolve_launch_file(str(cue))

        assert result != str(cue)
        assert result.endswith(".cue")
        fixed_content = open(result).read()
        assert "C:\\" not in fixed_content
        assert "CRASH 2.BIN" in fixed_content

    def test_fixed_cue_is_written_next_to_bin(self, driver, tmp_path):
        """The corrected .cue must be in the same directory as the .bin files."""
        (tmp_path / "game.bin").touch()
        cue = tmp_path / "game.cue"
        cue.write_text('FILE "C:\\game.bin" BINARY\n  TRACK 01 MODE2/2352\n')

        result = driver._resolve_launch_file(str(cue))

        from pathlib import Path
        assert Path(result).parent == tmp_path

    def test_fixed_cue_filename_has_dot_prefix(self, driver, tmp_path):
        """Fixed .cue gets a dot prefix so scanner ignores it."""
        (tmp_path / "game.bin").touch()
        cue = tmp_path / "game.cue"
        cue.write_text('FILE "C:\\game.bin" BINARY\n')

        result = driver._resolve_launch_file(str(cue))

        from pathlib import Path
        assert Path(result).name.startswith(".")

    def test_unchanged_when_bin_not_found(self, driver, tmp_path):
        """If we can't find the track file, return the original (RetroArch will error)."""
        cue = tmp_path / "game.cue"
        cue.write_text('FILE "C:\\missing.bin" BINARY\n')
        # No .bin file in tmp_path

        result = driver._resolve_launch_file(str(cue))
        assert result == str(cue)

    def test_absolute_unix_path_is_fixed(self, driver, tmp_path):
        """FILE "/mnt/roms/game.bin" (absolute Unix) is also a broken reference."""
        (tmp_path / "game.bin").touch()
        cue = tmp_path / "game.cue"
        cue.write_text('FILE "/mnt/roms/game.bin" BINARY\n')

        result = driver._resolve_launch_file(str(cue))
        assert result != str(cue)
        assert "game.bin" in open(result).read()
