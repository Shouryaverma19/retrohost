"""
Shared pytest fixtures and configuration.

On Windows the default tmp_path base (AppData/Local/Temp/pytest-of-<user>)
can be permission-denied when left from a previous session. We override it
to a local project directory that we always own.
"""
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP_BASE = Path(__file__).parent.parent / ".pytest_tmp"


@pytest.fixture()
def tmp_path() -> Path:
    """Override built-in tmp_path to use a local directory we always own."""
    _TMP_BASE.mkdir(exist_ok=True)
    d = Path(tempfile.mkdtemp(dir=_TMP_BASE))
    yield d
    shutil.rmtree(d, ignore_errors=True)
