"""Video encoder selection for FFmpeg transcodes.

Keeping encoder-specific options here makes it possible to add more hardware
encoders without changing HLS command construction.
"""

DEFAULT_VIDEO_ENCODER = 'libx264'
SUPPORTED_VIDEO_ENCODERS = frozenset({DEFAULT_VIDEO_ENCODER, 'h264_nvenc'})


def resolve_video_encoder(value: str | None, log=print) -> str:
    """Return a supported encoder, falling back safely to ``libx264``."""
    encoder = (value or DEFAULT_VIDEO_ENCODER).strip().lower()
    if encoder in SUPPORTED_VIDEO_ENCODERS:
        return encoder

    log(
        f"Unsupported FFMPEG_VIDEO_ENCODER={value!r}. "
        f"Supported values: {', '.join(sorted(SUPPORTED_VIDEO_ENCODERS))}. "
        f"Falling back to {DEFAULT_VIDEO_ENCODER}."
    )
    return DEFAULT_VIDEO_ENCODER


def build_video_encoder_args(encoder: str) -> list[str]:
    """Build output options for the selected H.264 video encoder.

    NVENC uses Turing's balanced ``p5`` preset and constant-quality VBR.  A
    CQ of 22 is the closest intentionally conservative counterpart to the
    existing libx264 CRF 22; it is not a bit-for-bit quality equivalence.
    """
    if encoder == 'libx264':
        return ['-c:v', 'libx264', '-crf', '22']
    if encoder == 'h264_nvenc':
        return [
            '-c:v', 'h264_nvenc',
            '-preset', 'p5',
            '-rc', 'vbr',
            '-cq', '22',
            '-b:v', '0',
        ]
    raise ValueError(f'Unsupported FFmpeg video encoder: {encoder}')
