"""
Тесты извлечения транскриптов YouTube с таймштампами
"""

import pytest
from unittest.mock import Mock, patch
import json
from youtube_processor import YouTubeProcessor

# Мок данных для тестирования
MOCK_VIDEO_INFO = {
    'title': 'Финансовые результаты компании 2024',
    'duration': 1800,  # 30 минут
    'uploader': 'Business Channel',
    'view_count': 150000,
    'description': 'Подробный разбор финансовых показателей компании за 2024 год. Рост выручки составил 25%, прибыль увеличилась до $2.5 млрд.',
    'subtitles': {
        'ru': [{'url': 'https://example.com/subtitles.vtt'}]
    }
}

MOCK_TRANSCRIPT_VTT = """
WEBVTT

00:00:15.000 --> 00:00:18.500
Добро пожаловать на презентацию результатов

00:00:30.000 --> 00:00:35.000
Выручка компании выросла на 25% и достигла 3.2 миллиарда рублей

00:01:45.000 --> 00:01:52.000
Чистая прибыль увеличилась до $150 миллионов, что превысило прогнозы

00:03:20.000 --> 00:03:28.000
EBITDA маржа составила 18.5% против 15.2% в прошлом году

00:05:10.000 --> 00:05:18.000
К концу 2025 года планируется достичь отметки в $500 миллионов выручки

00:12:30.000 --> 00:12:40.000
Инвестиции в R&D составят €75 миллионов в следующем квартале
"""

MOCK_TRANSCRIPT_WITH_TIMESTAMPS = [
    {'start': 15, 'end': 18.5, 'text': 'Добро пожаловать на презентацию результатов'},
    {'start': 30, 'end': 35, 'text': 'Выручка компании выросла на 25% и достигла 3.2 миллиарда рублей'},
    {'start': 105, 'end': 112, 'text': 'Чистая прибыль увеличилась до $150 миллионов, что превысило прогнозы'},
    {'start': 200, 'end': 208, 'text': 'EBITDA маржа составила 18.5% против 15.2% в прошлом году'},
    {'start': 310, 'end': 318, 'text': 'К концу 2025 года планируется достичь отметки в $500 миллионов выручки'},
    {'start': 750, 'end': 760, 'text': 'Инвестиции в R&D составят €75 миллионов в следующем квартале'},
]

class MockGroqClient:
    """Мок клиент Groq для тестирования"""
    
    @property
    def chat(self):
        return MockChat()

class MockChat:
    @property
    def completions(self):
        return MockCompletions()

class MockCompletions:
    def create(self, **kwargs):
        """Мок ответ с таймштампами в цифрах и фактах"""
        
        summary_with_timestamps = """
Компания представила отличные финансовые результаты за 2024 год с превышением всех прогнозов.

Ключевые достижения:
• Рост выручки на 25% до 3.2 миллиарда рублей
• Чистая прибыль $150 миллионов превысила ожидания
• EBITDA маржа улучшилась до 18.5%

Планы развития:
• Достижение $500 миллионов выручки к концу 2025 года
• Инвестиции в R&D €75 миллионов в следующем квартале

🔢 Цифры и факты:
— 25% рост выручки [00:30]
— 3.2 миллиарда рублей выручка [00:30]
— $150 миллионов чистая прибыль [01:45]
— 18.5% EBITDA маржа [03:20]
— $500 миллионов целевая выручка 2025 [05:10]
— €75 миллионов инвестиции в R&D [12:30]
        """
        
        return MockResponse(summary_with_timestamps.strip())

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)

class MockMessage:
    def __init__(self, content):
        self.content = content

def test_youtube_url_extraction():
    """Тест извлечения YouTube URL из текста"""
    
    processor = YouTubeProcessor()
    
    test_messages = [
        "Посмотрите это видео: https://www.youtube.com/watch?v=abc123",
        "Короткая ссылка: https://youtu.be/xyz789",
        "Встроенное видео: https://www.youtube.com/embed/def456",
        "Несколько ссылок: https://youtu.be/test1 и https://www.youtube.com/watch?v=test2"
    ]
    
    for message in test_messages:
        urls = processor.extract_youtube_urls(message)
        assert len(urls) > 0, f"Должны быть найдены URL в: {message}"
        
        for url_info in urls:
            assert 'url' in url_info
            assert 'video_id' in url_info
            assert url_info['url'].startswith('https://www.youtube.com/watch?v=')

def test_duration_limit_updated():
    """Тест обновленного лимита длительности (2 часа вместо 1)"""
    
    processor = YouTubeProcessor()
    
    # Мок yt-dlp для возврата информации о видео
    with patch('yt_dlp.YoutubeDL') as mock_ydl:
        mock_instance = Mock()
        mock_ydl.return_value.__enter__.return_value = mock_instance
        
        # Тест видео 1.5 часа (должно пройти)
        mock_instance.extract_info.return_value = {
            'title': 'Тест видео 1.5 часа',
            'duration': 5400,  # 1.5 часа в секундах
            'is_live': False
        }
        
        result = processor.validate_youtube_url("https://www.youtube.com/watch?v=test1")
        assert result['valid'] == True, "Видео 1.5 часа должно быть валидным"
        
        # Тест видео 2.5 часа (должно быть отклонено)
        mock_instance.extract_info.return_value = {
            'title': 'Тест видео 2.5 часа',
            'duration': 9000,  # 2.5 часа в секундах
            'is_live': False
        }
        
        result = processor.validate_youtube_url("https://www.youtube.com/watch?v=test2")
        assert result['valid'] == False, "Видео 2.5 часа должно быть отклонено"
        assert "более 2 часов" in result['error'], "Ошибка должна упоминать лимит 2 часа"

@patch('requests.get')
def test_transcript_extraction_with_timestamps(mock_get):
    """Тест извлечения транскрипта с сохранением таймштампов"""
    
    # Мок ответа с VTT субтитрами
    mock_response = Mock()
    mock_response.text = MOCK_TRANSCRIPT_VTT
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response
    
    processor = YouTubeProcessor()
    
    # Тестируем извлечение текста из VTT
    transcript_text = processor._extract_subtitle_text("https://example.com/subtitles.vtt")
    
    assert transcript_text != "", "Транскрипт должен быть извлечен"
    assert "25%" in transcript_text, "Процент должен сохраниться"
    assert "3.2 миллиарда" in transcript_text, "Сумма должна сохраниться"
    assert "$150 миллионов" in transcript_text, "Валюта должна сохраниться"

def test_timestamp_formatting():
    """Тест форматирования таймштампов mm:ss"""
    
    test_cases = [
        (15, "00:15"),      # 15 секунд
        (75, "01:15"),      # 1 минута 15 секунд
        (3661, "61:01"),    # Более часа
        (0, "00:00"),       # Начало
    ]
    
    for seconds, expected in test_cases:
        # Простая функция форматирования
        minutes = seconds // 60
        secs = seconds % 60
        formatted = f"{minutes:02d}:{secs:02d}"
        
        assert formatted == expected, f"Время {seconds}s должно форматироваться как {expected}"

@patch('yt_dlp.YoutubeDL')
@patch('requests.get')
def test_full_youtube_processing_with_timestamps(mock_get, mock_ydl):
    """Тест полного процесса обработки YouTube с таймштампами"""
    
    # Настраиваем мок для yt-dlp
    mock_instance = Mock()
    mock_ydl.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = MOCK_VIDEO_INFO
    
    # Настраиваем мок для получения субтитров
    mock_response = Mock()
    mock_response.text = MOCK_TRANSCRIPT_VTT
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response
    
    # Создаем процессор с мок клиентом
    groq_client = MockGroqClient()
    processor = YouTubeProcessor(groq_client)
    
    # Извлекаем информацию и субтитры
    result = processor.extract_video_info_and_subtitles("https://www.youtube.com/watch?v=test")
    
    assert result['success'] == True
    assert result['has_subtitles'] == True
    assert "25%" in result['text']  # Проверяем что числа есть в тексте
    
    # Тестируем суммаризацию с таймштампами
    summary_result = processor.summarize_youtube_content(
        result['text'], 
        result['title'], 
        result['duration']
    )
    
    assert summary_result['success'] == True
    
    summary = summary_result['summary']
    assert '🔢 Цифры и факты:' in summary, "Должен быть блок с цифрами и фактами"
    
    # Проверяем наличие таймштампов в формате [mm:ss]
    timestamp_patterns = ['[00:30]', '[01:45]', '[03:20]', '[05:10]', '[12:30]']
    
    found_timestamps = 0
    for pattern in timestamp_patterns:
        if pattern in summary:
            found_timestamps += 1
            print(f"✓ Найден таймштамп: {pattern}")
        else:
            print(f"✗ Отсутствует таймштамп: {pattern}")
    
    # Должно быть найдено минимум 80% таймштампов
    timestamp_rate = found_timestamps / len(timestamp_patterns)
    assert timestamp_rate >= 0.8, f"Найдено таймштампов: {timestamp_rate:.1%}"

def test_segment_processing():
    """Тест разбиения транскрипта на сегменты по времени"""
    
    # Симуляция разбиения 30-минутного видео на 5-минутные сегменты
    total_duration = 1800  # 30 минут
    segment_duration = 300  # 5 минут
    
    segments = []
    for start_time in range(0, total_duration, segment_duration):
        end_time = min(start_time + segment_duration, total_duration)
        segments.append({
            'start': start_time,
            'end': end_time,
            'duration': end_time - start_time
        })
    
    assert len(segments) == 6, "Должно быть 6 сегментов для 30-минутного видео"
    assert segments[0]['start'] == 0
    assert segments[-1]['end'] == total_duration
    
    # Проверяем что все сегменты покрывают полное время
    total_covered = sum(seg['duration'] for seg in segments)
    assert total_covered == total_duration

def test_fallback_without_subtitles():
    """Тест обработки видео без субтитров (только описание)"""
    
    video_info_no_subs = MOCK_VIDEO_INFO.copy()
    video_info_no_subs['subtitles'] = {}
    video_info_no_subs['automatic_captions'] = {}
    
    with patch('yt_dlp.YoutubeDL') as mock_ydl:
        mock_instance = Mock()
        mock_ydl.return_value.__enter__.return_value = mock_instance
        mock_instance.extract_info.return_value = video_info_no_subs
        
        processor = YouTubeProcessor()
        result = processor.extract_video_info_and_subtitles("https://www.youtube.com/watch?v=test")
        
        assert result['success'] == True
        assert result['has_subtitles'] == False
        assert result['has_description'] == True
        assert "ОПИСАНИЕ ВИДЕО:" in result['text']
        assert "25%" in result['text']  # Из описания

if __name__ == "__main__":
    pytest.main([__file__, "-v"])