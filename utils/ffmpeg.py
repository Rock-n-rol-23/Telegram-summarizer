"""
FFmpeg utilities for audio conversion and processing
Safe audio format conversion to WAV 16kHz mono
"""

import logging
import os
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

def check_ffmpeg() -> bool:
    """Check if FFmpeg is available"""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def to_wav_16k_mono(src_path: str, dst_path: str) -> bool:
    """
    Convert audio file to WAV 16kHz mono format
    
    Args:
        src_path: Source audio file path
        dst_path: Destination WAV file path
        
    Returns:
        True if conversion successful, False otherwise
    """
    if not check_ffmpeg():
        logger.error("FFmpeg not available")
        return False
    
    try:
        cmd = [
            'ffmpeg',
            '-i', src_path,
            '-ar', '16000',      # Sample rate 16kHz
            '-ac', '1',          # Mono
            '-acodec', 'pcm_s16le',  # PCM 16-bit
            '-y',                # Overwrite output
            dst_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes max
        )
        
        if result.returncode == 0:
            logger.info(f"Converted {src_path} -> {dst_path}")
            return True
        else:
            logger.error(f"FFmpeg conversion failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg conversion timed out")
        return False
    except Exception as e:
        logger.error(f"FFmpeg conversion error: {e}")
        return False

def get_audio_info(file_path: str) -> dict:
    """
    Get audio file information using ffprobe
    
    Returns:
        Dictionary with duration, format, channels, sample_rate
    """
    info = {
        "duration": 0.0,
        "format": "unknown",
        "channels": 0,
        "sample_rate": 0
    }
    
    if not check_ffmpeg():
        return info
    
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            
            # Get format info
            if 'format' in data:
                info["duration"] = float(data['format'].get('duration', 0))
                info["format"] = data['format'].get('format_name', 'unknown')
            
            # Get audio stream info
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'audio':
                    info["channels"] = int(stream.get('channels', 0))
                    info["sample_rate"] = int(stream.get('sample_rate', 0))
                    break
        
    except Exception as e:
        logger.warning(f"Failed to get audio info: {e}")
    
    return info

def extract_audio_from_video(video_path: str, audio_path: str) -> bool:
    """
    Extract audio track from video file
    
    Args:
        video_path: Input video file
        audio_path: Output audio file (WAV)
        
    Returns:
        True if extraction successful
    """
    if not check_ffmpeg():
        return False
    
    try:
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',              # No video
            '-ar', '16000',     # 16kHz
            '-ac', '1',         # Mono
            '-acodec', 'pcm_s16le',
            '-y',
            audio_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            logger.info(f"Extracted audio: {video_path} -> {audio_path}")
            return True
        else:
            logger.error(f"Audio extraction failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Audio extraction error: {e}")
        return False

def validate_audio_file(file_path: str) -> bool:
    """
    Validate if file is a valid audio file
    
    Args:
        file_path: Path to audio file
        
    Returns:
        True if valid audio file
    """
    info = get_audio_info(file_path)
    return info["duration"] > 0 and info["sample_rate"] > 0