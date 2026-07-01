"""Tests for the WebSocket input handler (ws_input.py).

Uses FastAPI TestClient (httpx + starlette) for WebSocket testing —
no real browser or network connection needed.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.ws_input as ws_module
from app.api.ws_input import router


@pytest.fixture(autouse=True)
def reset_active_ws():
    """Reset global WebSocket state before every test."""
    ws_module._active_ws = None
    yield
    ws_module._active_ws = None


@pytest.fixture()
def app_client() -> TestClient:
    """FastAPI app with only the ws_input router mounted."""
    application = FastAPI()
    application.include_router(router)
    return TestClient(application)


def _mock_player():
    """Return a mock PlayerService that accepts any call."""
    player = MagicMock()
    player.handle_input = MagicMock()
    player.release_all_inputs = MagicMock()
    return player


# ---------------------------------------------------------------------------
# Basic connectivity
# ---------------------------------------------------------------------------

class TestWsInputBasic:
    def test_connection_is_accepted(self, app_client):
        with patch("app.api.ws_input.get_player_service", return_value=_mock_player()):
            with app_client.websocket_connect("/ws/input") as ws:
                assert ws is not None  # connection established without error

    def test_valid_input_event_calls_handle_input(self, app_client):
        player = _mock_player()
        with patch("app.api.ws_input.get_player_service", return_value=player):
            with app_client.websocket_connect("/ws/input") as ws:
                ws.send_text(json.dumps({"key": "up", "pressed": True}))

        player.handle_input.assert_called_once_with("up", True)

    def test_release_is_called_on_disconnect(self, app_client):
        player = _mock_player()
        with patch("app.api.ws_input.get_player_service", return_value=player):
            with app_client.websocket_connect("/ws/input"):
                pass  # context exit triggers disconnect

        player.release_all_inputs.assert_called_once()

    def test_malformed_json_is_ignored(self, app_client):
        player = _mock_player()
        with patch("app.api.ws_input.get_player_service", return_value=player):
            with app_client.websocket_connect("/ws/input") as ws:
                ws.send_text("not valid json {{")
                ws.send_text(json.dumps({"key": "down", "pressed": False}))

        # malformed message ignored, valid one processed
        player.handle_input.assert_called_once_with("down", False)

    def test_missing_key_field_is_ignored(self, app_client):
        player = _mock_player()
        with patch("app.api.ws_input.get_player_service", return_value=player):
            with app_client.websocket_connect("/ws/input") as ws:
                ws.send_text(json.dumps({"pressed": True}))  # no "key"

        player.handle_input.assert_not_called()


# ---------------------------------------------------------------------------
# Single active client enforcement (code 4000)
# ---------------------------------------------------------------------------

class TestSingleActiveClient:
    def test_active_ws_is_set_on_connect(self, app_client):
        with patch("app.api.ws_input.get_player_service", return_value=_mock_player()):
            with app_client.websocket_connect("/ws/input"):
                assert ws_module._active_ws is not None

    def test_active_ws_is_cleared_on_disconnect(self, app_client):
        with patch("app.api.ws_input.get_player_service", return_value=_mock_player()):
            with app_client.websocket_connect("/ws/input"):
                pass

        assert ws_module._active_ws is None

    def test_second_client_replaces_first_in_active_ws(self, app_client):
        """When a second client connects, _active_ws must point to it."""
        with patch("app.api.ws_input.get_player_service", return_value=_mock_player()):
            with app_client.websocket_connect("/ws/input") as ws1:
                first_ws = ws_module._active_ws
                # Open second connection (TestClient runs synchronously,
                # so we capture the module state immediately after accept)
                with app_client.websocket_connect("/ws/input") as ws2:
                    second_ws = ws_module._active_ws
                    assert second_ws is not first_ws
