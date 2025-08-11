"""
FFmpeg utilities for safe audio transcoding
Converts various audio formats to WAV 16kHz mono for Whisper processing
"""

import subprocess
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def to_wav_16k_mono(src_path: str, dst_path: str, ffmpeg_path: str = "ffmpeg") -> None:
    """
    Convert audio file to WAV 16kHz mono format suitable for Whisper
    
    Args:
        src_path: Path to source audio file
        dst_path: Path to output WAV file  
        ffmpeg_path: Path to ffmpeg executable
        
    Raises:
        FileNotFoundError: If ffmpeg is not found
        subprocess.CalledProcessError: If conversion fails
        Exception: For other conversion errors
    """
    try:
        # Check if ffmpeg is available
        subprocess.run([ffmpeg_path, "-version"], 
                      capture_output=True, check=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise FileNotFoundError(f"FFmpeg not found at: {ffmpeg_path}")
    except subprocess.TimeoutExpired:
        raise Exception("FFmpeg version check timed out")
    
    # Ensure source file exists
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Source file not found: {src_path}")
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    
    # FFmpeg command for conversion to WAV 16kHz mono
    cmd = [
        ffmpeg_path,
        "-i", src_path,           # Input file
        "-ac", "1",               # Mono (1 channel)
        "-ar", "16000",           # 16kHz sample rate
        "-acodec", "pcm_s16le",   # PCM 16-bit little endian
        "-f", "wav",              # WAV format
        "-y",                     # Overwrite output file
        dst_path
    ]
    
    try:
        logger.info(f"Converting {src_path} to WAV 16kHz mono: {dst_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            check=True
        )
        
        # Verify output file was created
        if not os.path.exists(dst_path) or os.path.getsize(dst_path) == 0:
            raise Exception("Output file was not created or is empty")
            
        logger.info(f"Successfully converted to WAV: {dst_path}")
        
    except subprocess.TimeoutExpired:
        raise Exception(f"FFmpeg conversion timed out after 5 minutes")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        raise Exception(f"FFmpeg conversion failed: {error_msg}")


def extract_audio(src_path: str, dst_path: str, ffmpeg_path: str = "ffmpeg") -> None:
    """
    Extract audio track from video file (for video_note processing)
    
    Args:
        src_path: Path to source video file
        dst_path: Path to output audio file
        ffmpeg_path: Path to ffmpeg executable
        
    Raises:
        FileNotFoundError: If ffmpeg is not found
        subprocess.CalledProcessError: If extraction fails
        Exception: For other extraction errors
    """
    try:
        # Check if ffmpeg is available
        subprocess.run([ffmpeg_path, "-version"], 
                      capture_output=True, check=True, timeout=10)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise FileNotFoundError(f"FFmpeg not found at: {ffmpeg_path}")
    
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Source file not found: {src_path}")
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    
    # Extract audio and convert to suitable format
    cmd = [
        ffmpeg_path,
        "-i", src_path,           # Input video file
        "-vn",                    # No video
        "-ac", "1",               # Mono
        "-ar", "16000",           # 16kHz sample rate
        "-acodec", "pcm_s16le",   # PCM 16-bit little endian
        "-f", "wav",              # WAV format
        "-y",                     # Overwrite output file
        dst_path
    ]
    
    try:
        logger.info(f"Extracting audio from {src_path} to: {dst_path}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            check=True
        )
        
        # Verify output file was created
        if not os.path.exists(dst_path) or os.path.getsize(dst_path) == 0:
            raise Exception("Audio extraction failed - no output file")
            
        logger.info(f"Successfully extracted audio: {dst_path}")
        
    except subprocess.TimeoutExpired:
        raise Exception(f"Audio extraction timed out after 5 minutes")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        raise Exception(f"Audio extraction failed: {error_msg}")


def get_audio_duration(file_path: str, ffmpeg_path: str = "ffmpeg") -> Optional[float]:
    """
    Get duration of audio/video file in seconds using ffprobe
    
    Args:
        file_path: Path to audio/video file
        ffmpeg_path: Path to ffmpeg executable (ffprobe should be in same directory)
        
    Returns:
        Duration in seconds, or None if unable to determine
    """
    try:
        # Try ffprobe first (more accurate)
        ffprobe_path = ffmpeg_path.replace('ffmpeg', 'ffprobe')
        cmd = [
            ffprobe_path,
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
            
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass
    
    try:
        # Fallback to ffmpeg
        cmd = [
            ffmpeg_path,
            "-i", file_path,
            "-f", "null", "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # Parse duration from stderr
        import re
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
        if duration_match:
            hours, minutes, seconds = duration_match.groups()
            total_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            return total_seconds
            
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass
    
    logger.warning(f"Unable to determine duration for: {file_path}")
    return None


def check_ffmpeg_available(ffmpeg_path: str = "ffmpeg") -> bool:
    """
    Check if FFmpeg is available and working
    
    Args:
        ffmpeg_path: Path to ffmpeg executable
        
    Returns:
        True if FFmpeg is available, False otherwise
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-version"], 
            capture_output=True, 
            timeout=10,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False