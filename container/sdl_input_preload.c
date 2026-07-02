/* LD_PRELOAD para o RetroArch no container RetroHost.
 *
 * Motivo: no WSL2 não há udevd, então o input via uinput/udev não funciona
 * (o libudev não enumera os devices). Este preload contorna isso criando um
 * SDL2 *virtual joystick* DENTRO do processo do RetroArch (input_joypad_driver
 * =sdl2) — o SDL2 não depende de udev. Um socket UNIX recebe comandos de botão
 * do backend (SDLGamepadProvider) e os aplica ao joystick virtual.
 *
 * Protocolo do socket (SOCK_DGRAM, texto): "<tipo> <indice> <valor>\n"
 *   tipo "b": botão   -> indice 0..14,  valor 0/1
 *   tipo "h": hat     -> indice 0,      valor = bitmask SDL_HAT_* (up=1 right=2
 *                                       down=4 left=8), para o d-pad
 * Path do socket: env HOMEGAMES_INPUT_SOCK (default /tmp/homegames_input.sock).
 *
 * Compilar: gcc -shared -fPIC -o sdl_input_preload.so sdl_input_preload.c -ldl -lpthread
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>

typedef int (*SDL_Init_t)(unsigned int);
typedef int (*SDL_JoystickAttachVirtual_t)(int, int, int, int);
typedef int (*SDL_JoystickSetVirtualButton_t)(void *, int, unsigned char);
typedef int (*SDL_JoystickSetVirtualHat_t)(void *, int, unsigned char);
typedef void *(*SDL_JoystickOpen_t)(int);
typedef const char *(*SDL_GetError_t)(void);

#define SDL_INIT_JOYSTICK 0x00000200u
#define SDL_JOYSTICK_TYPE_GAMECONTROLLER 1

static void *g_joy = NULL;
static SDL_JoystickSetVirtualButton_t p_setbtn = NULL;
static SDL_JoystickSetVirtualHat_t p_sethat = NULL;

static const char *sock_path(void) {
    const char *p = getenv("HOMEGAMES_INPUT_SOCK");
    return p && *p ? p : "/tmp/homegames_input.sock";
}

static void *listener(void *arg) {
    void *handle = (void *)arg;
    SDL_JoystickAttachVirtual_t attach = dlsym(handle, "SDL_JoystickAttachVirtual");
    SDL_JoystickOpen_t open = dlsym(handle, "SDL_JoystickOpen");
    SDL_GetError_t geterr = dlsym(handle, "SDL_GetError");
    p_setbtn = dlsym(handle, "SDL_JoystickSetVirtualButton");
    p_sethat = dlsym(handle, "SDL_JoystickSetVirtualHat");
    if (!attach || !open || !p_setbtn) {
        fprintf(stderr, "[hg-preload] simbolos SDL virtual joystick ausentes\n");
        return NULL;
    }
    /* 6 eixos, 15 botões, 1 hat — gamepad padrão */
    int idx = attach(SDL_JOYSTICK_TYPE_GAMECONTROLLER, 6, 15, 1);
    if (idx < 0) {
        fprintf(stderr, "[hg-preload] AttachVirtual falhou: %s\n", geterr ? geterr() : "?");
        return NULL;
    }
    g_joy = open(idx);
    fprintf(stderr, "[hg-preload] virtual joystick criado (idx=%d)\n", idx);

    int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) { perror("[hg-preload] socket"); return NULL; }
    const char *path = sock_path();
    unlink(path);
    struct sockaddr_un addr = {0};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("[hg-preload] bind");
        return NULL;
    }
    fprintf(stderr, "[hg-preload] ouvindo input em %s\n", path);

    char buf[64];
    for (;;) {
        ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) continue;
        buf[n] = 0;
        char type;
        int index, value;
        if (sscanf(buf, " %c %d %d", &type, &index, &value) == 3 && g_joy) {
            if (type == 'b') p_setbtn(g_joy, index, (unsigned char)value);
            else if (type == 'h' && p_sethat) p_sethat(g_joy, index, (unsigned char)value);
        }
    }
    return NULL;
}

int SDL_Init(unsigned int flags) {
    static SDL_Init_t real = NULL;
    if (!real) real = (SDL_Init_t)dlsym(RTLD_NEXT, "SDL_Init");
    int rc = real(flags | SDL_INIT_JOYSTICK);
    void *handle = dlopen("libSDL2-2.0.so.0", RTLD_NOW | RTLD_GLOBAL);
    if (handle) {
        pthread_t t;
        pthread_create(&t, NULL, listener, handle);
        pthread_detach(t);
    } else {
        fprintf(stderr, "[hg-preload] dlopen libSDL2 falhou\n");
    }
    return rc;
}
