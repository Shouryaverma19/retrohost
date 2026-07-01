"""Interface de driver de emulador.

A API nunca deve falar diretamente com RetroArch ou qualquer outro emulador.
Toda interação passa por uma implementação concreta de EmulatorDriver, o que
permite trocar o backend de emulação (RetroArch, outro frontend libretro,
um emulador standalone, etc.) sem alterar a camada de serviços/API.
"""
from abc import ABC, abstractmethod
from typing import Any


class EmulatorDriverError(Exception):
    """Erro genérico de driver de emulador."""


class CoreNotConfiguredError(EmulatorDriverError):
    """Levantado quando o core necessário para o console não está disponível."""


class EmulatorDriver(ABC):
    @abstractmethod
    def launch(self, game: Any) -> None:
        """Inicia a execução de `game`. Não bloqueia a thread chamadora."""

    @abstractmethod
    def stop(self) -> None:
        """Encerra o processo em execução, se houver."""

    @abstractmethod
    def status(self) -> bool:
        """Retorna True se um jogo está atualmente em execução."""

    def pause(self) -> None:
        raise NotImplementedError("pause() ainda não é suportado por este driver")

    def resume(self) -> None:
        raise NotImplementedError("resume() ainda não é suportado por este driver")

    def save_state(self) -> None:
        raise NotImplementedError("save_state() ainda não é suportado por este driver")

    def load_state(self) -> None:
        raise NotImplementedError("load_state() ainda não é suportado por este driver")

    def screenshot(self) -> None:
        raise NotImplementedError("screenshot() ainda não é suportado por este driver")
