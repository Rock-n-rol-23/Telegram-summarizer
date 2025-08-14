import os, tempfile
from pydub import AudioSegment
from utils.ffmpeg import ensure_ffmpeg
from audio_processor import AudioProcessor
from groq import Groq

print("ffmpeg:", ensure_ffmpeg())
sine = AudioSegment.silent(duration=1500)  # 1.5 сек тишины
tmpdir = tempfile.mkdtemp()
src = os.path.join(tmpdir, "test.ogg")
wav = os.path.join(tmpdir, "test.wav")
sine.export(src, format="ogg")  # проверяем экспорт через ffmpeg
print("OGG written:", os.path.exists(src))

ap = AudioProcessor(groq_client=Groq(api_key=os.getenv("GROQ_API_KEY", "dummy")))
duration, rate = ap._convert_to_wav16k_mono(src, wav)
print("WAV:", os.path.exists(wav), "duration:", duration, "rate:", rate)