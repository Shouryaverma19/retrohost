"""Auto-detecção do encoder de vídeo do ffmpeg que funciona nesta máquina.

A imagem do container é agnóstica de GPU: a MESMA imagem roda em NVIDIA, Intel,
AMD ou só CPU. Em vez de confiar em "o encoder está compilado" ou "o device
existe" (frágil), testamos cada candidato com um encode-probe REAL — um ffmpeg
curto (testsrc -> encoder -> null). O primeiro que retorna 0 é usado.

Probe usa exatamente os mesmos args do perfil real (encoder_profiles), incluindo
filtros de hwupload do VAAPI/QSV, para não passar no probe e falhar no stream.

Resultado cacheado: a detecção roda uma vez por processo, não a cada jogo.
"""
import subprocess

from app.streaming.encoder_profiles import AUTO_DETECT_ORDER, EncoderProfile, get_profile

_PROBE_DURATION = "0.3"  # segundos de vídeo sintético por probe
_PROBE_SIZE = "256x240"  # resolução pequena, probe rápido
_cached_encoder: str | None = None


def _probe(profile: EncoderProfile) -> bool:
    """True se o ffmpeg consegue encodar de fato com este perfil."""
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        *profile.pre_input,
        "-f", "lavfi", "-i", f"testsrc=size={_PROBE_SIZE}:rate=30",
        "-t", _PROBE_DURATION,
        *profile.filter_args,
        *profile.codec_args,
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def detect_encoder() -> str:
    """Retorna o nome do melhor encoder que funciona (cacheado).

    Testa na ordem nvenc > qsv > vaapi > libx264. libx264 é o fim-da-linha
    (encoda por software, sempre disponível) — se nada de hardware funcionar,
    cai nele garantidamente.
    """
    global _cached_encoder
    if _cached_encoder is not None:
        return _cached_encoder
    for name in AUTO_DETECT_ORDER:
        if _probe(get_profile(name)):
            _cached_encoder = name
            return name
    # Em teoria inalcançável (libx264 sempre passa), mas fail-safe explícito.
    _cached_encoder = "libx264"
    return _cached_encoder


def describe_encoder(name: str) -> str:
    """Descrição amigável para log (qual hardware está sendo usado)."""
    return {
        "h264_nvenc": "h264_nvenc (GPU NVIDIA)",
        "h264_qsv": "h264_qsv (Intel QuickSync)",
        "h264_vaapi": "h264_vaapi (GPU via VAAPI - Intel/AMD)",
        "libx264": "libx264 (CPU/software - nenhuma GPU detectada)",
        "h264_v4l2m2m": "h264_v4l2m2m (encoder de hardware do Raspberry Pi)",
    }.get(name, name)
