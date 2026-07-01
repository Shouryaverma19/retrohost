"""Interface de entrada remota (gamepad do navegador -> dispositivo de input no Pi).

Implementação concreta: UInputKeyboardProvider (app/input/uinput_keyboard.py),
que expõe um teclado virtual via /dev/uinput, lido pelo RetroArch
(input_driver=udev) como se fosse um teclado USB físico.
"""
from abc import ABC, abstractmethod


class InputProvider(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Cria/registra o dispositivo de input. Idempotente se já conectado."""

    @abstractmethod
    def disconnect(self) -> None:
        """Remove o dispositivo de input, se existir. Idempotente."""

    @abstractmethod
    def press(self, key: str) -> None:
        """Sinaliza tecla pressionada. `key` é um nome lógico (ver keymap.py)."""

    @abstractmethod
    def release(self, key: str) -> None:
        """Sinaliza tecla solta."""

    @abstractmethod
    def release_all(self) -> None:
        """Solta todas as teclas atualmente pressionadas (ex: desconexão abrupta)."""
