"""
YouTube Video Processor для Telegram бота
Извлекает субтитры и описание, суммаризует через Groq API
"""

import re
import os
import tempfile
import shutil
import logging
import yt_dlp
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class YouTubeProcessor:
    def __init__(self, groq_client=None):
        self.groq_client = groq_client
        self.cookies_file = Path("cookies.txt")
        
    def _has_valid_cookies(self) -> bool:
        """Проверяет наличие валидных cookies"""
        if not self.cookies_file.exists():
            return False
        
        content = self.cookies_file.read_text(encoding='utf-8')
        # Проверяем, что файл содержит реальные cookies, а не только комментарии
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        cookie_lines = [line for line in lines if not line.startswith('#')]
        return len(cookie_lines) > 0
        
    def _get_ydl_opts_with_cookies(self, base_opts: dict) -> dict:
        """Добавляет cookies к настройкам yt-dlp если они доступны"""
        opts = base_opts.copy()
        if self._has_valid_cookies():
            opts['cookiefile'] = str(self.cookies_file)
            logger.info(f"📁 Используем cookies из {self.cookies_file}")
        else:
            logger.warning(f"⚠️ Cookies файл пуст или отсутствует: {self.cookies_file}")
        return opts
        
    def extract_youtube_urls(self, text: str) -> List[Dict[str, str]]:
        """Извлекает YouTube URL из текста сообщения"""
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]+)'
        ]
        
        youtube_urls = []
        for pattern in youtube_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                video_id = match.group(1)
                full_url = f"https://www.youtube.com/watch?v={video_id}"
                youtube_urls.append({
                    'url': full_url,
                    'video_id': video_id,
                    'original_url': match.group(0)
                })
        
        return youtube_urls

    def validate_youtube_url(self, url: str) -> Dict[str, Any]:
        """Проверяет доступность YouTube видео"""
        # Проверяем наличие cookies
        if not self._has_valid_cookies():
            return {
                'valid': False,
                'error': '❌ Необходимо добавить cookies для обработки YouTube ссылок (см. README)'
            }
            
        try:
            base_opts = {
                'quiet': True,
                'no_warnings': True,
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_skip': ['configs', 'webpage'],
                        'player_client': ['android', 'web']
                    }
                },
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            
            ydl_opts = self._get_ydl_opts_with_cookies(base_opts)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                duration = info.get('duration', 0)
                max_duration = 7200  # 2 часа по новому лимиту
                if duration > max_duration:
                    return {
                        'valid': False,
                        'error': f'Видео слишком длинное (более {max_duration//3600} часов)'
                    }
                
                if info.get('is_live'):
                    return {
                        'valid': False,
                        'error': 'Прямые трансляции не поддерживаются'
                    }
                
                return {
                    'valid': True,
                    'title': info.get('title', 'Без названия'),
                    'duration': duration,
                    'uploader': info.get('uploader', 'Неизвестно'),
                    'view_count': info.get('view_count', 0)
                }
                
        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"❌ Ошибка валидации YouTube: {e}")
            
            # Проверяем тип ошибки
            if 'sign in' in error_str or 'bot' in error_str:
                return {
                    'valid': False,
                    'error': '❌ Cookies для YouTube истекли или невалидны. Просьба обновить cookies (см. README)'
                }
            elif 'cookies' in error_str:
                return {
                    'valid': False,
                    'error': '❌ Проблема с cookies. Просьба проверить формат файла cookies.txt'
                }
            
            return {
                'valid': False,
                'error': f'Ошибка при проверке видео: {str(e)}'
            }

    def extract_video_info_and_subtitles(self, url: str, max_duration: int = 3600) -> Dict[str, Any]:
        """Извлекает информацию о видео и субтитры"""
        # Проверяем наличие cookies
        if not self._has_valid_cookies():
            return {
                'success': False,
                'error': '❌ Необходимо добавить cookies для обработки YouTube ссылок (см. README)'
            }
            
        try:
            base_opts = {
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitlesformat': 'vtt',
                'subtitleslangs': ['ru', 'en', 'auto'],
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_skip': ['configs', 'webpage'],
                        'player_client': ['android', 'web']
                    }
                },
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }
            
            ydl_opts = self._get_ydl_opts_with_cookies(base_opts)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                duration = info.get('duration', 0)
                if duration > max_duration:
                    raise Exception(f"Видео слишком длинное: {duration//60} минут")
                
                # Извлекаем субтитры
                subtitles_text = ""
                description = info.get('description', '') or ""
                
                # Пытаемся получить субтитры
                subtitles = info.get('subtitles', {})
                automatic_captions = info.get('automatic_captions', {})
                
                # Сначала пытаемся найти русские субтитры
                if 'ru' in subtitles:
                    subtitles_text = self._extract_subtitle_text(subtitles['ru'][0]['url'])
                elif 'ru' in automatic_captions:
                    subtitles_text = self._extract_subtitle_text(automatic_captions['ru'][0]['url'])
                # Потом английские
                elif 'en' in subtitles:
                    subtitles_text = self._extract_subtitle_text(subtitles['en'][0]['url'])
                elif 'en' in automatic_captions:
                    subtitles_text = self._extract_subtitle_text(automatic_captions['en'][0]['url'])
                
                # Комбинируем текст из субтитров и описания
                combined_text = ""
                if subtitles_text:
                    combined_text += f"СУБТИТРЫ ВИДЕО:\n{subtitles_text}\n\n"
                if description and len(description) > 100:
                    combined_text += f"ОПИСАНИЕ ВИДЕО:\n{description[:2000]}\n"
                
                if not combined_text:
                    return {
                        'success': False,
                        'error': 'Нет доступных субтитров или описания для анализа'
                    }
                
                return {
                    'success': True,
                    'text': combined_text,
                    'title': info.get('title', 'Без названия'),
                    'duration': duration,
                    'uploader': info.get('uploader', 'Неизвестно'),
                    'view_count': info.get('view_count', 0),
                    'has_subtitles': bool(subtitles_text),
                    'has_description': bool(description)
                }
            
        except Exception as e:
            error_str = str(e).lower()
            logger.error(f"❌ Ошибка извлечения данных YouTube: {e}")
            
            # Проверяем тип ошибки
            if 'sign in' in error_str or 'bot' in error_str:
                return {
                    'success': False,
                    'error': '❌ Cookies для YouTube истекли или невалидны. Просьба обновить cookies (см. README)'
                }
            elif 'cookies' in error_str:
                return {
                    'success': False,
                    'error': '❌ Проблема с cookies. Просьба проверить формат файла cookies.txt'
                }
            
            return {
                'success': False,
                'error': f'Ошибка при извлечении данных видео: {str(e)}'
            }

    def _extract_subtitle_text(self, subtitle_url: str) -> str:
        """Извлекает текст из субтитров VTT формата"""
        try:
            import requests
            response = requests.get(subtitle_url, timeout=30)
            response.raise_for_status()
            
            # Парсим VTT формат
            lines = response.text.split('\n')
            text_lines = []
            
            for line in lines:
                line = line.strip()
                # Пропускаем заголовки VTT и временные метки
                if (line and 
                    not line.startswith('WEBVTT') and
                    not line.startswith('NOTE') and
                    not '-->' in line and
                    not line.isdigit()):
                    # Убираем HTML теги если есть
                    import re
                    clean_line = re.sub(r'<[^>]+>', '', line)
                    if clean_line and len(clean_line) > 2:
                        text_lines.append(clean_line)
            
            return ' '.join(text_lines)
            
        except Exception as e:
            logger.error(f"Ошибка извлечения субтитров: {e}")
            return ""



    def summarize_youtube_content(self, content: str, video_title: str = "", video_duration: int = 0) -> Dict[str, Any]:
        """Создает резюме контента YouTube видео через Groq API"""
        try:
            logger.info(f"🎬 Начало суммаризации YouTube: {video_title[:50]}...")
            logger.info(f"🎬 Длина контента: {len(content)} символов, длительность: {video_duration} сек")
            
            if not self.groq_client:
                logger.error("🎬 Groq API клиент не инициализирован")
                return {
                    'success': False,
                    'error': 'Groq API клиент не инициализирован'
                }
            
            # Ограничиваем длину контента
            max_chars = 10000
            if len(content) > max_chars:
                content = content[:max_chars] + "...\n[Контент обрезан для обработки]"
            
            # Определяем длину резюме
            if video_duration < 600:  # Менее 10 минут
                summary_length = "150-250 слов"
                max_tokens = 300
            elif video_duration < 1800:  # Менее 30 минут
                summary_length = "250-400 слов"
                max_tokens = 450
            else:  # Более 30 минут
                summary_length = "400-600 слов"
                max_tokens = 600
            
            duration_str = f"{video_duration//60} минут {video_duration%60} секунд"
            
            prompt = f"""Создай структурированное резюме YouTube видео на русском языке.

ИНФОРМАЦИЯ О ВИДЕО:
Название: {video_title}
Длительность: {duration_str}

ТРЕБОВАНИЯ К РЕЗЮМЕ:
- Объем: {summary_length}
- Структура: основная тема, ключевые моменты, главные выводы
- Используй маркированные списки для ключевых идей
- Сохрани важные факты, цифры, имена
- Пиши понятным и структурированным языком

КОНТЕНТ ВИДЕО:
{content}

СТРУКТУРИРОВАННОЕ РЕЗЮМЕ:"""

            logger.info(f"🎬 Отправка запроса к Groq API, макс. токенов: {max_tokens}")
            completion = self.groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system", 
                        "content": "Ты эксперт по созданию качественных резюме видеоконтента. Создавай четкие, информативные и полезные саммари на русском языке."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                model="llama-3.3-70b-versatile",
                max_tokens=max_tokens,
                temperature=0.3
            )
            logger.info(f"🎬 Получен ответ от Groq API")
            
            summary = completion.choices[0].message.content.strip()
            logger.info(f"🎬 Суммаризация завершена успешно, длина резюме: {len(summary)} символов")
            
            return {
                'success': True,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"🎬 Ошибка суммаризации Groq: {e}")
            logger.error(f"🎬 Тип ошибки: {type(e)}")
            return {
                'success': False,
                'error': f'Ошибка суммаризации Groq: {str(e)}'
            }

    def create_fallback_summary(self, content: str, video_title: str = "") -> Dict[str, Any]:
        """Простое резюме без AI как запасной вариант"""
        try:
            sentences = content.split('.')
            sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
            
            # Берем ключевые предложения
            summary_sentences = []
            if len(sentences) > 0:
                summary_sentences.append(sentences[0])  # Начало
            if len(sentences) > 4:
                summary_sentences.append(sentences[len(sentences)//3])  # Треть
                summary_sentences.append(sentences[2*len(sentences)//3])  # Две трети
            if len(sentences) > 1:
                summary_sentences.append(sentences[-1])  # Конец
            
            summary = '. '.join(summary_sentences)
            
            if len(summary) > 1000:
                summary = summary[:1000] + "..."
            
            summary += "\n\n⚠️ Автоматическое извлечение (AI суммаризация недоступна)"
            
            return {
                'success': True,
                'summary': summary
            }
            
        except Exception as e:
            logger.error(f"Ошибка fallback резюме: {e}")
            return {
                'success': False,
                'error': f'Ошибка fallback резюме: {e}'
            }

