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

logger = logging.getLogger(__name__)

class YouTubeProcessor:
    def __init__(self, groq_client=None):
        self.groq_client = groq_client
        
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
        try:
            ydl_opts = {
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
            # Если основной метод не работает, пробуем альтернативный подход
            error_str = str(e).lower()
            if ('sign in' in error_str or 'bot' in error_str or 'cookies' in error_str or 
                'not available on this app' in error_str or 'content is not available' in error_str):
                logger.warning(f"⚠️ YouTube антибот защита обнаружена, пробуем альтернативный метод")
                try:
                    # Альтернативный метод - только основная информация
                    simple_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'format': 'worst',  # Минимальный формат
                        'simulate': True,   # Симуляция без загрузки
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                        }
                    }
                    
                    with yt_dlp.YoutubeDL(simple_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        return {
                            'valid': True,
                            'title': info.get('title', 'Видео YouTube'),
                            'duration': info.get('duration', 0),
                            'uploader': info.get('uploader', 'Неизвестно'),
                            'view_count': info.get('view_count', 0),
                            'warning': 'Ограниченная информация из-за защиты YouTube'
                        }
                except Exception as e2:
                    logger.error(f"Альтернативный метод также неудачен: {e2}")
            
            return {
                'valid': False,
                'error': f'Ошибка при проверке видео: {str(e)}'
            }

    def extract_video_info_and_subtitles(self, url: str, max_duration: int = 3600) -> Dict[str, Any]:
        """Извлекает информацию о видео и субтитры"""
        try:
            ydl_opts = {
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
            logger.error(f"Ошибка извлечения информации о видео: {e}")
            error_str = str(e).lower()
            
            # Если это антибот защита, пробуем fallback метод
            if ('sign in' in error_str or 'bot' in error_str or 'cookies' in error_str or 
                'not available on this app' in error_str or 'content is not available' in error_str):
                logger.warning(f"⚠️ YouTube антибот защита, пробуем fallback без субтитров")
                try:
                    # Fallback: только базовая информация без субтитров
                    simple_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'skip_download': True,
                        'simulate': True,
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                        }
                    }
                    
                    with yt_dlp.YoutubeDL(simple_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        
                        # Используем только описание, если доступно
                        description = info.get('description', '') or ""
                        if description and len(description) > 50:
                            combined_text = f"ОПИСАНИЕ ВИДЕО:\n{description[:3000]}\n\n[Субтитры недоступны из-за защиты YouTube]"
                        else:
                            combined_text = f"Видео: {info.get('title', 'Без названия')}\n\n[Субтитры и описание недоступны из-за защиты YouTube]"
                        
                        return {
                            'success': True,
                            'text': combined_text,
                            'title': info.get('title', 'Видео YouTube'),
                            'duration': info.get('duration', 0),
                            'uploader': info.get('uploader', 'Неизвестно'),
                            'view_count': info.get('view_count', 0),
                            'warning': 'Ограниченные данные из-за защиты YouTube'
                        }
                        
                except Exception as e2:
                    logger.error(f"Fallback метод также неудачен: {e2}")
            
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

