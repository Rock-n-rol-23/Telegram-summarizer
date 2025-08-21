
import tempfile
import os

class WhisperModel:
    def __init__(self, model_size, device='cpu', compute_type='int8'):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        
    def transcribe(self, audio_path, language=None, **kwargs):
        # Simple mock transcription - in production this would be real ASR
        segments = [
            type('Segment', (), {
                'start': 0.0,
                'end': 5.0, 
                'text': 'Пример транскрипции аудио сообщения'
            })()
        ]
        
        info = type('Info', (), {
            'language': language or 'ru',
            'duration': 5.0
        })()
        
        return segments, info
        
def available_models():
    return ['tiny', 'small', 'medium', 'large']
