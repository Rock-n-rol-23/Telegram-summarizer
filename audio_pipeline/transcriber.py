"""
Unified ASR transcriber with multiple offline engines
Supports vosk, Hugging Face wav2vec2, and speechbrain
"""

import logging
import os
import json
import time
from typing import Dict, Any, Optional
import tempfile

logger = logging.getLogger(__name__)

# Global cache for loaded models
_models = {}

def transcribe_audio(file_path: str, language_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Transcribe audio using available ASR engines
    
    Args:
        file_path: Path to WAV audio file (16kHz mono)
        language_hint: Language hint ('ru', 'en', etc.)
    
    Returns:
        {
            "text": str,
            "language": str,
            "duration_sec": float,
            "engine": str,
            "chunks": int
        }
    """
    result = {
        "text": "",
        "language": "unknown",
        "duration_sec": 0.0,
        "engine": "none",
        "chunks": 1
    }
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    # Get audio duration
    try:
        import soundfile as sf
        data, samplerate = sf.read(file_path)
        result["duration_sec"] = len(data) / samplerate
    except Exception as e:
        logger.warning(f"Could not determine audio duration: {e}")
    
    # Determine ASR engine to use
    asr_engine = os.getenv("ASR_ENGINE", "auto")
    
    if asr_engine == "auto":
        # Try engines in priority order
        for engine in ["vosk", "hf_wav2vec_ru", "speechbrain"]:
            try:
                engine_result = _transcribe_with_engine(file_path, engine, language_hint)
                if engine_result and engine_result.get("text"):
                    result.update(engine_result)
                    result["engine"] = engine
                    logger.info(f"Successfully transcribed with engine: {engine}")
                    return result
            except Exception as e:
                logger.warning(f"Engine {engine} failed: {e}")
                continue
    else:
        # Use specific engine
        try:
            engine_result = _transcribe_with_engine(file_path, asr_engine, language_hint)
            if engine_result:
                result.update(engine_result)
                result["engine"] = asr_engine
                return result
        except Exception as e:
            logger.error(f"Specified engine {asr_engine} failed: {e}")
    
    # Fallback response
    result["text"] = f"""[ТРАНСКРИПЦИЯ НЕДОСТУПНА]

ASR движки недоступны. Проверьте установку:
• vosk: pip install vosk
• Hugging Face: pip install transformers torch
• SpeechBrain: pip install speechbrain

Длительность аудио: {result['duration_sec']:.1f} сек
Обработка завершена без транскрипции."""
    
    result["language"] = language_hint or "ru"
    result["engine"] = "fallback"
    
    return result

def _transcribe_with_engine(file_path: str, engine: str, language_hint: Optional[str]) -> Optional[Dict[str, Any]]:
    """Transcribe with specific engine"""
    
    if engine == "vosk":
        return _transcribe_vosk(file_path, language_hint)
    elif engine == "hf_wav2vec_ru":
        return _transcribe_hf_wav2vec(file_path, language_hint)
    elif engine == "speechbrain":
        return _transcribe_speechbrain(file_path, language_hint)
    else:
        raise ValueError(f"Unknown ASR engine: {engine}")

def _transcribe_vosk(file_path: str, language_hint: Optional[str]) -> Optional[Dict[str, Any]]:
    """Transcribe using Vosk"""
    try:
        import vosk
        import json
        import wave
        
        # Determine model based on language
        if language_hint and language_hint.startswith('en'):
            model_name = "vosk-model-en-us-0.22"
            model_url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
        else:
            model_name = "vosk-model-ru-0.42"
            model_url = "https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip"
        
        # Download and load model
        model = _get_vosk_model(model_name, model_url)
        if not model:
            raise RuntimeError("Failed to load Vosk model")
        
        # Create recognizer
        rec = vosk.KaldiRecognizer(model, 16000)
        rec.SetWords(True)
        
        # Open audio file
        wf = wave.open(file_path, 'rb')
        
        # Process audio
        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result.get('text'):
                    results.append(result['text'])
        
        # Get final result
        final_result = json.loads(rec.FinalResult())
        if final_result.get('text'):
            results.append(final_result['text'])
        
        wf.close()
        
        # Combine results
        full_text = ' '.join(results).strip()
        
        return {
            "text": full_text,
            "language": language_hint or "ru",
            "chunks": len(results)
        }
        
    except ImportError:
        logger.warning("Vosk not installed")
        return None
    except Exception as e:
        logger.error(f"Vosk transcription error: {e}")
        return None

def _transcribe_hf_wav2vec(file_path: str, language_hint: Optional[str]) -> Optional[Dict[str, Any]]:
    """Transcribe using Hugging Face Wav2Vec2"""
    try:
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        import torch
        import soundfile as sf
        
        # Load model for Russian
        model_name = "jonatasgrosman/wav2vec2-large-xlsr-53-russian"
        
        # Get cached model
        if model_name not in _models:
            logger.info(f"Loading HF model: {model_name}")
            processor = Wav2Vec2Processor.from_pretrained(model_name, cache_dir="./models")
            model = Wav2Vec2ForCTC.from_pretrained(model_name, cache_dir="./models")
            _models[model_name] = (processor, model)
        
        processor, model = _models[model_name]
        
        # Load audio
        speech, sample_rate = sf.read(file_path)
        
        # Resample if needed
        if sample_rate != 16000:
            import librosa
            speech = librosa.resample(speech, orig_sr=sample_rate, target_sr=16000)
        
        # Process
        inputs = processor(speech, sampling_rate=16000, return_tensors="pt", padding=True)
        
        with torch.no_grad():
            logits = model(inputs.input_values).logits
        
        # Decode
        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = processor.decode(predicted_ids[0])
        
        return {
            "text": transcription,
            "language": "ru",
            "chunks": 1
        }
        
    except ImportError:
        logger.warning("Transformers/torch not installed")
        return None
    except Exception as e:
        logger.error(f"HF Wav2Vec2 transcription error: {e}")
        return None

def _transcribe_speechbrain(file_path: str, language_hint: Optional[str]) -> Optional[Dict[str, Any]]:
    """Transcribe using SpeechBrain"""
    try:
        from speechbrain.pretrained import EncoderDecoderASR
        
        # Load Russian ASR model
        model_name = "speechbrain/asr-crdnn-rnnlm-librispeech"
        
        if model_name not in _models:
            logger.info(f"Loading SpeechBrain model: {model_name}")
            asr_model = EncoderDecoderASR.from_hparams(
                source=model_name,
                savedir="./models/speechbrain"
            )
            _models[model_name] = asr_model
        
        asr_model = _models[model_name]
        
        # Transcribe
        transcription = asr_model.transcribe_file(file_path)
        
        return {
            "text": transcription,
            "language": language_hint or "en",
            "chunks": 1
        }
        
    except ImportError:
        logger.warning("SpeechBrain not installed")
        return None
    except Exception as e:
        logger.error(f"SpeechBrain transcription error: {e}")
        return None

def _get_vosk_model(model_name: str, model_url: str):
    """Download and load Vosk model"""
    try:
        import vosk
        import zipfile
        import urllib.request
        
        models_dir = "./models"
        os.makedirs(models_dir, exist_ok=True)
        
        model_path = os.path.join(models_dir, model_name)
        
        # Check if model exists
        if os.path.exists(model_path):
            return vosk.Model(model_path)
        
        # Download model
        logger.info(f"Downloading Vosk model: {model_name}")
        zip_path = os.path.join(models_dir, f"{model_name}.zip")
        
        urllib.request.urlretrieve(model_url, zip_path)
        
        # Extract model
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(models_dir)
        
        # Remove zip file
        os.remove(zip_path)
        
        return vosk.Model(model_path)
        
    except Exception as e:
        logger.error(f"Failed to download/load Vosk model: {e}")
        return None

def get_available_engines() -> list:
    """Get list of available ASR engines"""
    engines = []
    
    try:
        import vosk
        engines.append("vosk")
    except ImportError:
        pass
    
    try:
        import transformers
        import torch
        engines.append("hf_wav2vec_ru")
    except ImportError:
        pass
    
    try:
        import speechbrain
        engines.append("speechbrain")
    except ImportError:
        pass
    
    return engines