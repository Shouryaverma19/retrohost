"""Mapa: nome lógico de tecla -> índice de botão no joystick virtual SDL (ver
container/sdl_input_preload.c). Usado pelo SDLGamepadProvider no container.

O virtual joystick é reconhecido pela SDL como um SDL_GameController com este
mapping (confirmado via SDL_GameControllerMappingForDeviceIndex):
  a:b0 b:b1 x:b2 y:b3 back:b4 guide:b5 start:b6 leftstick:b7 rightstick:b8
  leftshoulder:b9 rightshoulder:b10 dpup:b11 dpdown:b12 dpleft:b13 dpright:b14
IMPORTANTE: o d-pad é exposto como BOTÕES (b11-b14), não como hat — por isso
todas as entradas usam índice de botão.

Os nomes lógicos ("a","b","up"...) são o vocabulário do frontend/WebSocket,
iguais aos do keymap.py (caminho uinput). O RetroPad lógico mapeia assim:
RetroPad B = SDL A(b0), RetroPad A = SDL B(b1) — convenção dos autoconfigs
para pads Xbox-style; ajustável aqui se sair trocado no teste real.
"""

# nome lógico -> índice de botão SDL
SDL_BUTTON_MAP: dict[str, int] = {
    "b": 0,       # RetroPad B  -> SDL A (sul)
    "a": 1,       # RetroPad A  -> SDL B (leste)
    "y": 2,       # RetroPad Y  -> SDL X (oeste)
    "x": 3,       # RetroPad X  -> SDL Y (norte)
    "select": 4,  # back
    "start": 6,   # start
    "l": 9,       # leftshoulder
    "r": 10,      # rightshoulder
    "up": 11,     # dpup
    "down": 12,   # dpdown
    "left": 13,   # dpleft
    "right": 14,  # dpright
}
