# utils/ffmpeg.py
import os
from imageio_ffmpeg import get_ffmpeg_exe

_FFMPEG_PATH = None

def ensure_ffmpeg() -> str:
    global _FFMPEG_PATH
    if _FFMPEG_PATH and os.path.exists(_FFMPEG_PATH):
        return _FFMPEG_PATH
    path = get_ffmpeg_exe()
    _FFMPEG_PATH = path
    return path