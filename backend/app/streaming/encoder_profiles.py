"""Perfis de encoder de vídeo do ffmpeg, agnósticos de GPU.

Cada perfil descreve os args do ffmpeg para um encoder H.264 específico,
divididos em três posições porque encoders por hardware (VAAPI/QSV) precisam
injetar args ANTES do input (-vaapi_device / -init_hw_device) e um filtro de
upload para a GPU (-vf), não só o -c:v:

    ffmpeg <pre_input> -i <fifo> -fps_mode passthrough <filter> <codec> ...

O detector (encoder_detect.py) e o FFmpegStreamingProvider usam EXATAMENTE os
mesmos args (via build_video_args), para o encode-probe testar o caminho real —
um probe simplificado poderia passar e o stream real falhar.

Ordem de preferência para auto-detecção: nvenc > qsv > vaapi > libx264.
libx264 (software) é o fim-da-linha, sempre funciona (sem GPU).
"""
from dataclasses import dataclass, field

# /dev/dri/renderD128 é o render node padrão (Intel/AMD). Configurável por env
# em config.py se a máquina tiver múltiplas GPUs.
DEFAULT_RENDER_NODE = "/dev/dri/renderD128"


@dataclass(frozen=True)
class EncoderProfile:
    name: str
    # args antes de "-i <fifo>" (ex: -vaapi_device, -init_hw_device)
    pre_input: list[str] = field(default_factory=list)
    # filtro de vídeo (-vf ...), ex: upload do frame para a GPU
    filter_args: list[str] = field(default_factory=list)
    # args do codec (-c:v ... e tuning)
    codec_args: list[str] = field(default_factory=list)


def _vaapi_profile(render_node: str = DEFAULT_RENDER_NODE) -> EncoderProfile:
    # VAAPI: aponta o device, sobe o frame (nv12) para a GPU e encoda.
    return EncoderProfile(
        name="h264_vaapi",
        pre_input=["-vaapi_device", render_node],
        filter_args=["-vf", "format=nv12,hwupload"],
        codec_args=["-c:v", "h264_vaapi", "-b:v", "4M", "-g", "30", "-bf", "0"],
    )


def _qsv_profile(render_node: str = DEFAULT_RENDER_NODE) -> EncoderProfile:
    # Intel QuickSync via QSV. Usa o mesmo render node.
    return EncoderProfile(
        name="h264_qsv",
        pre_input=["-init_hw_device", f"qsv=hw,child_device={render_node}", "-filter_hw_device", "hw"],
        filter_args=["-vf", "format=nv12,hwupload=extra_hw_frames=8"],
        codec_args=["-c:v", "h264_qsv", "-preset", "veryfast", "-b:v", "4M", "-g", "30", "-bf", "0"],
    )


# Perfis sem hardware-upload (codec puro). nvenc e v4l2m2m sao acelerados mas
# aceitam o frame de software direto; libx264 e software.
_SIMPLE_PROFILES: dict[str, list[str]] = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll",
                   "-b:v", "4M", "-g", "30", "-bf", "0"],
    # -bf 0: WebRTC NÃO aceita H.264 com B-frames (o navegador rejeita o stream
    # com "doesn't support H264 streams with B-frames"). O -tune zerolatency do
    # x264 deveria zerar B-frames, mas não é garantido em todos os builds — por
    # isso forçamos -bf 0 explicitamente. Vale para qualquer encoder.
    "libx264": ["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-b:v", "4M", "-g", "30", "-bf", "0"],
    "h264_v4l2m2m": ["-c:v", "h264_v4l2m2m", "-b:v", "2M", "-g", "15"],
}


def get_profile(name: str, render_node: str = DEFAULT_RENDER_NODE) -> EncoderProfile:
    if name == "h264_vaapi":
        return _vaapi_profile(render_node)
    if name == "h264_qsv":
        return _qsv_profile(render_node)
    if name in _SIMPLE_PROFILES:
        return EncoderProfile(name=name, codec_args=_SIMPLE_PROFILES[name])
    raise ValueError(
        f"Encoder '{name}' desconhecido. Opções: "
        f"{', '.join(['h264_nvenc', 'h264_qsv', 'h264_vaapi', 'libx264', 'h264_v4l2m2m'])}."
    )


# Ordem de preferência da auto-detecção (melhor latência/qualidade primeiro;
# libx264 por último, sempre funciona).
AUTO_DETECT_ORDER = ["h264_nvenc", "h264_qsv", "h264_vaapi", "libx264"]
