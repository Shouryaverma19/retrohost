"""Teclado virtual via Linux uinput, usado para traduzir estado de gamepad do
navegador em teclas que o RetroArch lê via input_driver=udev (como se fosse
um teclado USB físico plugado no Pi).

Requer: módulo uinput carregado, /dev/uinput acessível pelo usuário do
serviço (ver scripts/setup_input.sh) e o pacote de sistema python3-evdev
(NÃO via pip — ver backend/requirements.txt; recompilar evdev no Pi 3
teria o mesmo custo de build que motivou abandonar uvicorn[standard]).

No container (WSL2) não há udevd para criar o /dev/input/eventN quando o
uinput registra o device — sem esse node, nem o evdev relê as capabilities
nem o RetroArch (input_driver=udev) enxerga o teclado. Com
HOMEGAMES_MKNOD_INPUT=1, criamos o node manualmente via mknod lendo o
major:minor de /sys (ver _ensure_event_node). No Pi isso fica desligado
(o udev do sistema já cria o node).
"""
import os
import stat

from app.core.config import settings
from app.input.base import InputProvider
from app.input.keymap import EVDEV_KEYCODES

try:
    import evdev
except ImportError:  # ambiente sem python3-evdev (ex: dev no Windows)
    evdev = None


class UInputNotAvailableError(RuntimeError):
    pass


class UInputKeyboardProvider(InputProvider):
    def __init__(self, device_name: str = "RetroHost Virtual Keyboard") -> None:
        self._device_name = device_name
        self._device = None
        self._pressed_keys: set[str] = set()

    def connect(self) -> None:
        if self._device is not None:
            return
        if evdev is None:
            raise UInputNotAvailableError(
                "python3-evdev não está disponível. Rode scripts/setup_input.sh no Pi."
            )
        capabilities = {evdev.ecodes.EV_KEY: list(EVDEV_KEYCODES.values())}
        self._device = evdev.UInput(capabilities, name=self._device_name)
        if settings.MKNOD_INPUT:
            self._ensure_event_node()

    def _ensure_event_node(self) -> None:
        """Cria /dev/input/eventN para o device recém-registrado, se faltar.

        Em ambientes sem udevd (container WSL2), o uinput registra o device em
        /sys/devices/virtual/input/inputN/eventN mas nenhum node aparece em
        /dev/input. Lemos o major:minor do sysfs e criamos o node via mknod.
        Best-effort: qualquer falha é ignorada (o RetroArch dará o erro claro).
        """
        # Varremos o sysfs procurando o input com o nosso device_name e criamos
        # o node /dev/input/eventN correspondente.
        try:
            os.makedirs("/dev/input", exist_ok=True)
            base = "/sys/devices/virtual/input"
            for input_dir in os.listdir(base):
                name_file = os.path.join(base, input_dir, "name")
                if not os.path.exists(name_file):
                    continue
                with open(name_file) as fh:
                    if fh.read().strip() != self._device_name:
                        continue
                for entry in os.listdir(os.path.join(base, input_dir)):
                    if not entry.startswith("event"):
                        continue
                    node = f"/dev/input/{entry}"
                    if os.path.exists(node):
                        continue
                    with open(os.path.join(base, input_dir, entry, "dev")) as fh:
                        major, minor = (int(x) for x in fh.read().strip().split(":"))
                    os.mknod(node, stat.S_IFCHR | 0o660, os.makedev(major, minor))
        except OSError:
            pass

    def disconnect(self) -> None:
        if self._device is None:
            return
        self._device.close()
        self._device = None
        self._pressed_keys.clear()

    def press(self, key: str) -> None:
        if self._emit(key, 1):
            self._pressed_keys.add(key)

    def release(self, key: str) -> None:
        if self._emit(key, 0):
            self._pressed_keys.discard(key)

    def release_all(self) -> None:
        for key in list(self._pressed_keys):
            self.release(key)

    def _emit(self, key: str, value: int) -> bool:
        if self._device is None:
            return False
        code = EVDEV_KEYCODES.get(key)
        if code is None:
            return False
        self._device.write(evdev.ecodes.EV_KEY, code, value)
        self._device.syn()
        return True
