"""Tests for encoder auto-detection logic (encoder_detect.py).

All tests mock subprocess.run so they never call ffmpeg — fast and hermetic.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

import app.streaming.encoder_detect as encoder_detect_module
from app.streaming.encoder_detect import _probe, describe_encoder, detect_encoder
from app.streaming.encoder_profiles import get_profile


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the module-level cache before every test."""
    encoder_detect_module._cached_encoder = None
    yield
    encoder_detect_module._cached_encoder = None


def _make_result(returncode: int) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    return result


# ---------------------------------------------------------------------------
# _probe
# ---------------------------------------------------------------------------

class TestProbe:
    def test_returns_true_when_ffmpeg_exits_zero(self):
        with patch("subprocess.run", return_value=_make_result(0)):
            assert _probe(get_profile("libx264")) is True

    def test_returns_false_when_ffmpeg_exits_nonzero(self):
        with patch("subprocess.run", return_value=_make_result(1)):
            assert _probe(get_profile("libx264")) is False

    def test_returns_false_on_oserror(self):
        with patch("subprocess.run", side_effect=OSError("ffmpeg not found")):
            assert _probe(get_profile("libx264")) is False

    def test_returns_false_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 15)):
            assert _probe(get_profile("libx264")) is False

    def test_vaapi_profile_pre_input_included_in_command(self):
        """VAAPI probe must include -vaapi_device so it tests the real path."""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return _make_result(0)

        with patch("subprocess.run", side_effect=fake_run):
            _probe(get_profile("h264_vaapi"))

        assert "-vaapi_device" in captured["cmd"]

    def test_qsv_profile_pre_input_included_in_command(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return _make_result(0)

        with patch("subprocess.run", side_effect=fake_run):
            _probe(get_profile("h264_qsv"))

        assert "-init_hw_device" in captured["cmd"]


# ---------------------------------------------------------------------------
# detect_encoder — fallback chain
# ---------------------------------------------------------------------------

class TestDetectEncoder:
    def test_returns_first_working_encoder(self):
        # Only h264_nvenc passes
        def fake_run(cmd, **kwargs):
            if "h264_nvenc" in cmd:
                return _make_result(0)
            return _make_result(1)

        with patch("subprocess.run", side_effect=fake_run):
            assert detect_encoder() == "h264_nvenc"

    def test_falls_back_through_chain(self):
        # nvenc and qsv fail, vaapi passes
        def fake_run(cmd, **kwargs):
            if "h264_vaapi" in cmd:
                return _make_result(0)
            return _make_result(1)

        with patch("subprocess.run", side_effect=fake_run):
            assert detect_encoder() == "h264_vaapi"

    def test_falls_back_to_libx264_when_all_hw_fail(self):
        def fake_run(cmd, **kwargs):
            if "libx264" in cmd:
                return _make_result(0)
            return _make_result(1)

        with patch("subprocess.run", side_effect=fake_run):
            assert detect_encoder() == "libx264"

    def test_result_is_cached(self):
        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_result(0)

        with patch("subprocess.run", side_effect=fake_run):
            detect_encoder()
            detect_encoder()
            detect_encoder()

        # Only the probes for the first call should have run
        assert call_count == 1

    def test_cache_is_reset_between_tests(self):
        # This test verifies the autouse fixture works — cache must be None here
        assert encoder_detect_module._cached_encoder is None


# ---------------------------------------------------------------------------
# describe_encoder
# ---------------------------------------------------------------------------

class TestDescribeEncoder:
    def test_known_encoders_return_friendly_string(self):
        assert "NVIDIA" in describe_encoder("h264_nvenc")
        assert "QuickSync" in describe_encoder("h264_qsv")
        assert "VAAPI" in describe_encoder("h264_vaapi")
        assert "CPU" in describe_encoder("libx264")
        assert "Raspberry Pi" in describe_encoder("h264_v4l2m2m")

    def test_unknown_encoder_returns_name_itself(self):
        assert describe_encoder("some_unknown_encoder") == "some_unknown_encoder"
