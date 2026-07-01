"""Mapa: nome lógico de tecla -> keycode evdev/uinput, e índice de botão do
Gamepad API (mapping "standard") -> nome lógico.

Os nomes lógicos ("a", "b", "up", "start"...) correspondem aos binds atuais
de input_player1_* em retroarch.cfg (a="x", b="z", up="up", start="enter",
etc — confirmado em /home/YOUR_USER/.config/retroarch/retroarch.cfg no Pi real).
São também o vocabulário usado nas mensagens WebSocket do frontend.

Os keycodes abaixo são constantes inteiras hardcoded (não `import evdev`)
para este módulo continuar importável em qualquer ambiente (Windows dev,
testes) sem precisar de python3-evdev instalado — só uinput_keyboard.py
(o único lugar que de fato fala com o kernel) depende de evdev existir.
Valores conferem com linux/input-event-codes.h.
"""

EVDEV_KEYCODES: dict[str, int] = {
    "a": 45,  # KEY_X
    "b": 44,  # KEY_Z
    "x": 31,  # KEY_S
    "y": 30,  # KEY_A
    "l": 16,  # KEY_Q
    "r": 17,  # KEY_W
    "select": 54,  # KEY_RIGHTSHIFT
    "start": 28,  # KEY_ENTER
    "up": 103,  # KEY_UP
    "down": 108,  # KEY_DOWN
    "left": 105,  # KEY_LEFT
    "right": 106,  # KEY_RIGHT
}

# Índice de botão do Gamepad API ("standard" mapping) -> nome lógico acima.
#
# Nota: o botão 0 (posição física "A" num pad estilo Xbox) mapeia para "b",
# e o botão 1 ("B" físico) mapeia para "a" — convenção usada pelos próprios
# perfis de autoconfig do libretro para pads Xbox-style. Não validado ainda
# com um controle físico real; se os botões saírem trocados no teste real,
# basta inverter esse par aqui (sem mudança de arquitetura).
#
# Índices sem entrada (6, 7 = L2/R2; 10, 11 = L3/R3) ficam de fora
# deliberadamente — "nul" (sem bind) no RetroArch hoje, sem efeito.
GAMEPAD_BUTTON_TO_KEY: dict[int, str] = {
    0: "b",
    1: "a",
    2: "y",
    3: "x",
    4: "l",
    5: "r",
    8: "select",
    9: "start",
    12: "up",
    13: "down",
    14: "left",
    15: "right",
}
