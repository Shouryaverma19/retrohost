"""WebSocket de input remoto: navegador envia eventos de botão de gamepad,
backend traduz para teclas no teclado virtual uinput (ver app/input/).

Apenas UM cliente ativo por vez — quando um novo conecta, o anterior é
fechado com código 4000 ("controle assumido"). O frontend detecta esse
código e volta para a idle view sem encerrar o jogo.

Sem autenticação — projeto pessoal de uso doméstico em LAN, único usuário.
"""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.player import get_player_service

router = APIRouter()

_active_ws: WebSocket | None = None


@router.websocket("/ws/input")
async def input_ws(websocket: WebSocket) -> None:
    global _active_ws
    await websocket.accept()

    # Fecha o cliente anterior, se houver, sinalizando que o controle foi assumido.
    previous = _active_ws
    _active_ws = websocket
    if previous is not None:
        try:
            await previous.close(code=4000)
        except Exception:
            pass

    player = get_player_service()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                key = msg["key"]
                pressed = bool(msg["pressed"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            player.handle_input(key, pressed)
    except WebSocketDisconnect:
        pass
    finally:
        if _active_ws is websocket:
            _active_ws = None
        player.release_all_inputs()
