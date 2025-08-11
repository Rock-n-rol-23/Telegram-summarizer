"""
Vosk-based ASR transcriber с поддержкой множественных движков
Railway production-ready с умными fallback'ами
"""
import os
import logging
import shutil

logger = logging.getLogger(__name__)

def check_ffmpeg() -> bool:
    """Проверка доступности FFmpeg"""
    return shutil.which("ffmpeg") is not None

def get_available_engines() -> list:
    """
    Получает список доступных ASR движков
    
    Returns:
        list: ["vosk", "huggingface", "speechbrain"] или []
    """
    available = []
    
    # Проверяем Vosk
    try:
        import vosk
        available.append("vosk")
        logger.info("✅ Vosk ASR доступен")
    except ImportError:
        logger.info("❌ Vosk не установлен (pip install vosk==0.3.45)")
    
    # Проверяем Hugging Face Transformers
    try:
        import transformers
        import torch
        available.append("huggingface")
        logger.info("✅ Hugging Face Transformers доступен")
    except ImportError:
        logger.info("❌ Transformers не установлен (pip install transformers torch)")
    
    # Проверяем SpeechBrain
    try:
        import speechbrain
        available.append("speechbrain")
        logger.info("✅ SpeechBrain доступен")
    except ImportError:
        logger.info("❌ SpeechBrain не установлен (pip install speechbrain)")
    
    return available

def transcribe_audio(wav_file_path: str, language_hint: str = None) -> dict:
    """
    Транскрибирует аудио через доступные ASR движки
    
    Args:
        wav_file_path: путь к WAV файлу (16kHz mono)
        language_hint: язык ("ru", "en", None для автоопределения)
        
    Returns:
        dict: {"text": "...", "engine": "...", "error": "..." or None}
    """
    available_engines = get_available_engines()
    
    if not available_engines:
        return {
            "text": "",
            "engine": "none",
            "error": "ASR движки не установлены. Установите: pip install vosk==0.3.45"
        }
    
    # Пробуем движки по приоритету
    for engine in available_engines:
        try:
            if engine == "vosk":
                result = transcribe_with_vosk(wav_file_path, language_hint)
                if result:
                    return {"text": result, "engine": "vosk", "error": None}
                    
            elif engine == "huggingface":
                result = transcribe_with_huggingface(wav_file_path, language_hint)
                if result:
                    return {"text": result, "engine": "huggingface", "error": None}
                    
            elif engine == "speechbrain":
                result = transcribe_with_speechbrain(wav_file_path, language_hint)
                if result:
                    return {"text": result, "engine": "speechbrain", "error": None}
                    
        except Exception as e:
            logger.error(f"Ошибка {engine}: {e}")
            continue
    
    return {
        "text": "",
        "engine": "failed",
        "error": f"Все ASR движки ({', '.join(available_engines)}) не смогли обработать аудио"
    }

def transcribe_with_vosk(wav_file_path: str, language_hint: str = None) -> str:
    """Транскрипция через Vosk"""
    try:
        import vosk
        import json
        import wave
        
        # Определяем модель по языку
        if language_hint == "ru":
            model_path = "vosk-model-ru-0.42"
        elif language_hint == "en":
            model_path = "vosk-model-en-us-0.22"
        else:
            # По умолчанию русская модель
            model_path = "vosk-model-ru-0.42"
        
        # Проверяем, есть ли модель
        if not os.path.exists(model_path):
            logger.warning(f"Vosk модель {model_path} не найдена. Нужно скачать.")
            return None
        
        # Инициализируем модель
        model = vosk.Model(model_path)
        recognizer = vosk.KaldiRecognizer(model, 16000)
        
        # Открываем WAV файл
        with wave.open(wav_file_path, 'rb') as wf:
            results = []
            
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                    
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    if "text" in result and result["text"]:
                        results.append(result["text"])
            
            # Финальный результат
            final_result = json.loads(recognizer.FinalResult())
            if "text" in final_result and final_result["text"]:
                results.append(final_result["text"])
        
        # Объединяем результаты
        text = " ".join(results).strip()
        logger.info(f"Vosk транскрипция: {len(text)} символов")
        return text if text else None
        
    except Exception as e:
        logger.error(f"Ошибка Vosk: {e}")
        return None

def transcribe_with_huggingface(wav_file_path: str, language_hint: str = None) -> str:
    """Транскрипция через Hugging Face Wav2Vec2"""
    try:
        import torch
        import librosa
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Tokenizer
        
        # Выбираем модель по языку
        if language_hint == "ru":
            model_name = "bond005/wav2vec2-large-ru-golos"
        else:
            model_name = "facebook/wav2vec2-large-960h"
        
        # Загружаем модель и токенизатор
        tokenizer = Wav2Vec2Tokenizer.from_pretrained(model_name)
        model = Wav2Vec2ForCTC.from_pretrained(model_name)
        
        # Загружаем аудио
        speech, sample_rate = librosa.load(wav_file_path, sr=16000)
        
        # Токенизируем
        input_values = tokenizer(speech, return_tensors="pt", sampling_rate=16000).input_values
        
        # Инференс
        with torch.no_grad():
            logits = model(input_values).logits
        
        # Декодируем
        predicted_ids = torch.argmax(logits, dim=-1)
        transcription = tokenizer.decode(predicted_ids[0])
        
        logger.info(f"Hugging Face транскрипция: {len(transcription)} символов")
        return transcription.strip() if transcription else None
        
    except Exception as e:
        logger.error(f"Ошибка Hugging Face: {e}")
        return None

def transcribe_with_speechbrain(wav_file_path: str, language_hint: str = None) -> str:
    """Транскрипция через SpeechBrain"""
    try:
        from speechbrain.pretrained import EncoderDecoderASR
        
        # Выбираем модель
        if language_hint == "ru":
            model_name = "speechbrain/asr-crdnn-rnnlm-librispeech"  # Заглушка, нужна русская модель
        else:
            model_name = "speechbrain/asr-crdnn-rnnlm-librispeech"
        
        # Загружаем модель
        asr_model = EncoderDecoderASR.from_hparams(source=model_name)
        
        # Транскрибируем
        transcription = asr_model.transcribe_file(wav_file_path)
        
        logger.info(f"SpeechBrain транскрипция: {len(transcription)} символов")
        return transcription.strip() if transcription else None
        
    except Exception as e:
        logger.error(f"Ошибка SpeechBrain: {e}")
        return None

def download_vosk_model(language: str = "ru") -> bool:
    """
    Скачивает Vosk модель для языка
    
    Args:
        language: "ru" или "en"
        
    Returns:
        bool: успешность скачивания
    """
    try:
        import requests
        import zipfile
        
        if language == "ru":
            url = "https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip"
            model_name = "vosk-model-ru-0.42"
        elif language == "en":
            url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
            model_name = "vosk-model-en-us-0.22"
        else:
            return False
        
        if os.path.exists(model_name):
            logger.info(f"Модель {model_name} уже существует")
            return True
        
        logger.info(f"Скачивание модели {model_name}...")
        
        # Скачиваем
        response = requests.get(url, stream=True)
        zip_path = f"{model_name}.zip"
        
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Распаковываем
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall('.')
        
        # Удаляем архив
        os.remove(zip_path)
        
        logger.info(f"Модель {model_name} успешно скачана")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка скачивания модели: {e}")
        return False

# Функция для проверки работоспособности
if __name__ == "__main__":
    print("🔍 Проверка ASR движков...")
    
    engines = get_available_engines()
    print(f"Доступные движки: {engines}")
    
    ffmpeg_ok = check_ffmpeg()
    print(f"FFmpeg: {'✅' if ffmpeg_ok else '❌'}")
    
    if not engines:
        print("📋 Для установки движков:")
        print("  pip install vosk==0.3.45")
        print("  pip install transformers torch")
        print("  pip install speechbrain")