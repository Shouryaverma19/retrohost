"""InputProvider que injeta input num joystick virtual SDL2 vivendo dentro do
processo do RetroArch (via container/sdl_input_preload.c), por um socket UNIX.

Usado no container (especialmente WSL2), onde o caminho uinput/udev não funciona
por falta de udevd. Selecionado por settings.INPUT_PROVIDER=sdl (env
HOMEGAMES_INPUT_PROVIDER). O Pi continua usando UInputKeyboardProvider.

Protocolo (igual ao do preload): datagramas de texto "b <btn> <0|1>".
O d-pad é exposto como botões (b11-b14), então tudo são botões simples.
"""
import socket

from app.core.config import settings
from app.input.base import InputProvider
from app.input.sdl_keymap import SDL_BUTTON_MAP


class SDLGamepadProvider(InputProvider):
    def __init__(self, sock_path: str | None = None) -> None:
        self._sock_path = sock_path or settings.INPUT_SOCK_PATH
        self._sock: socket.socket | None = None
        self._pressed: set[str] = set()

    def connect(self) -> None:
        if self._sock is None:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

    def disconnect(self) -> None:
        self.release_all()
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def press(self, key: str) -> None:
        if self._emit(key, 1):
            self._pressed.add(key)

    def release(self, key: str) -> None:
        if self._emit(key, 0):
            self._pressed.discard(key)

    def release_all(self) -> None:
        for key in list(self._pressed):
            self.release(key)

    def _emit(self, key: str, value: int) -> bool:
        index = SDL_BUTTON_MAP.get(key)
        if index is None or self._sock is None:
            return False
        try:
            self._sock.sendto(f"b {index} {value}".encode(), self._sock_path)
        except OSError:
            # o preload pode ainda não ter criado o socket (jogo iniciando);
            # input perdido é tolerável (o usuário repete a tecla).
            return False
        return True
