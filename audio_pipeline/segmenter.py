"""
Audio segmentation and VAD (Voice Activity Detection)
Splits long audio files into manageable chunks for processing
"""

import os
import logging
import tempfile
from typing import List, Tuple, Optional
import asyncio

logger = logging.getLogger(__name__)

class AudioSegmenter:
    """Handles audio segmentation and voice activity detection"""
    
    def __init__(self, vad_enabled: bool = True):
        self.vad_enabled = vad_enabled
        self._vad_model = None
    
    def _initialize_vad(self) -> bool:
        """Initialize VAD model (lazy loading)"""
        if not self.vad_enabled:
            return False
            
        try:
            # Try to use webrtcvad (lightweight)
            import webrtcvad
            self._vad_model = webrtcvad.Vad(2)  # Aggressiveness level 0-3
            logger.info("WebRTC VAD initialized")
            return True
        except ImportError:
            logger.warning("webrtcvad not available, using simple segmentation")
            
        try:
            # Fallback to silero-vad (more accurate but heavier)
            import torch
            torch.hub.load(repo_or_dir='snakers4/silero-vad',
                          model='silero_vad',
                          force_reload=False,
                          onnx=False)
            logger.info("Silero VAD initialized")
            return True
        except Exception as e:
            logger.warning(f"Silero VAD not available: {e}")
        
        return False
    
    async def segment_audio(
        self,
        wav_path: str,
        enable_vad: bool = True,
        target_len_sec: int = 45,
        overlap_sec: int = 5,
        max_chunks: int = 20
    ) -> List[str]:
        """
        Segment audio file into chunks
        
        Args:
            wav_path: Path to WAV file (16kHz mono)
            enable_vad: Whether to use voice activity detection
            target_len_sec: Target segment length in seconds
            overlap_sec: Overlap between segments in seconds  
            max_chunks: Maximum number of chunks to create
            
        Returns:
            List of paths to segmented audio files
        """
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"Audio file not found: {wav_path}")
        
        # Get audio duration
        try:
            from utils.ffmpeg import get_audio_duration
            duration = get_audio_duration(wav_path)
            if duration is None:
                raise Exception("Could not determine audio duration")
        except Exception as e:
            logger.error(f"Error getting duration: {e}")
            return [wav_path]  # Return original file if can't segment
        
        logger.info(f"Segmenting audio: {duration:.1f}s into {target_len_sec}s chunks")
        
        # If audio is short enough, don't segment
        if duration <= target_len_sec * 1.2:  # 20% buffer
            logger.info("Audio short enough, no segmentation needed")
            return [wav_path]
        
        # Use VAD if available and enabled
        if enable_vad and self._initialize_vad():
            return await self._segment_with_vad(
                wav_path, target_len_sec, overlap_sec, max_chunks
            )
        else:
            return await self._segment_fixed_length(
                wav_path, target_len_sec, overlap_sec, max_chunks
            )
    
    async def _segment_fixed_length(
        self,
        wav_path: str,
        target_len_sec: int,
        overlap_sec: int,
        max_chunks: int
    ) -> List[str]:
        """Simple fixed-length segmentation"""
        try:
            from utils.ffmpeg import get_audio_duration
            duration = get_audio_duration(wav_path)
            
            if duration is None:
                return [wav_path]
            
            segments = []
            temp_dir = tempfile.mkdtemp(prefix="audio_segments_")
            
            step_sec = target_len_sec - overlap_sec
            current_start = 0
            chunk_num = 0
            
            while current_start < duration and chunk_num < max_chunks:
                # Calculate segment end
                segment_end = min(current_start + target_len_sec, duration)
                
                # Create output filename
                output_path = os.path.join(
                    temp_dir, 
                    f"segment_{chunk_num:03d}.wav"
                )
                
                # Extract segment using ffmpeg
                success = await self._extract_segment(
                    wav_path, output_path, current_start, segment_end
                )
                
                if success:
                    segments.append(output_path)
                    logger.info(f"Created segment {chunk_num}: {current_start:.1f}s - {segment_end:.1f}s")
                else:
                    logger.warning(f"Failed to create segment {chunk_num}")
                
                current_start += step_sec
                chunk_num += 1
            
            logger.info(f"Created {len(segments)} segments")
            return segments
            
        except Exception as e:
            logger.error(f"Fixed-length segmentation failed: {e}")
            return [wav_path]
    
    async def _segment_with_vad(
        self,
        wav_path: str,
        target_len_sec: int,
        overlap_sec: int,
        max_chunks: int
    ) -> List[str]:
        """VAD-based segmentation (more sophisticated)"""
        try:
            # For now, fall back to fixed-length
            # TODO: Implement proper VAD-based segmentation
            logger.info("VAD segmentation not fully implemented, using fixed-length")
            return await self._segment_fixed_length(
                wav_path, target_len_sec, overlap_sec, max_chunks
            )
            
        except Exception as e:
            logger.error(f"VAD segmentation failed: {e}")
            return await self._segment_fixed_length(
                wav_path, target_len_sec, overlap_sec, max_chunks
            )
    
    async def _extract_segment(
        self,
        input_path: str,
        output_path: str,
        start_sec: float,
        end_sec: float
    ) -> bool:
        """Extract audio segment using ffmpeg"""
        try:
            import subprocess
            
            duration = end_sec - start_sec
            
            cmd = [
                "ffmpeg",
                "-i", input_path,
                "-ss", str(start_sec),        # Start time
                "-t", str(duration),          # Duration
                "-ac", "1",                   # Mono
                "-ar", "16000",               # 16kHz
                "-acodec", "pcm_s16le",       # PCM 16-bit
                "-f", "wav",                  # WAV format
                "-y",                         # Overwrite
                output_path
            ]
            
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
            )
            
            if result.returncode == 0 and os.path.exists(output_path):
                return True
            else:
                logger.error(f"Segment extraction failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error extracting segment: {e}")
            return False
    
    def estimate_segments(self, duration_sec: float, target_len_sec: int = 45, overlap_sec: int = 5) -> int:
        """Estimate number of segments that will be created"""
        if duration_sec <= target_len_sec * 1.2:
            return 1
        
        step_sec = target_len_sec - overlap_sec
        return int((duration_sec - overlap_sec) / step_sec) + 1
    
    @staticmethod
    def cleanup_segments(segment_paths: List[str]) -> None:
        """Clean up segmented audio files"""
        for path in segment_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"Cleaned up segment: {path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup segment {path}: {e}")
        
        # Also try to remove the temp directory if empty
        if segment_paths:
            temp_dir = os.path.dirname(segment_paths[0])
            try:
                if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.debug(f"Could not remove temp directory: {e}")
    
    def get_vad_status(self) -> dict:
        """Get VAD availability status"""
        return {
            "vad_enabled": self.vad_enabled,
            "vad_initialized": self._vad_model is not None,
            "webrtcvad_available": self._check_webrtcvad(),
            "silero_available": self._check_silero()
        }
    
    def _check_webrtcvad(self) -> bool:
        """Check if webrtcvad is available"""
        try:
            import webrtcvad
            return True
        except ImportError:
            return False
    
    def _check_silero(self) -> bool:
        """Check if silero-vad is available"""
        try:
            import torch
            # Don't actually load the model, just check if torch is available
            return True
        except ImportError:
            return False