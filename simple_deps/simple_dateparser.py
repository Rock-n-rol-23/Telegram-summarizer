"""
Простой парсер дат для замены dateparser
"""

import re
from datetime import datetime, date
from typing import Optional

def parse_date(text: str, languages: list = None) -> Optional[datetime]:
    """Простой парсер дат без внешних зависимостей"""
    
    if not text:
        return None
    
    text = text.strip().lower()
    
    # Паттерны для русских дат
    ru_patterns = [
        # DD месяц YYYY
        (r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(\d{4}))?', 
         {'январ': 1, 'феврал': 2, 'март': 3, 'апрел': 4, 'ма': 5, 'июн': 6, 
          'июл': 7, 'август': 8, 'сентябр': 9, 'октябр': 10, 'ноябр': 11, 'декабр': 12}),
        
        # DD.MM.YYYY or DD/MM/YYYY
        (r'(\d{1,2})[./](\d{1,2})[./](\d{2,4})', None),
        
        # YYYY-MM-DD
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', None),
    ]
    
    # EN patterns
    en_patterns = [
        # Month DD, YYYY
        (r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})',
         {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
          'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12}),
    ]
    
    # Пробуем русские паттерны
    for pattern, month_map in ru_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                if month_map:  # Текстовый месяц
                    day = int(match.group(1))
                    month_text = match.group(2)
                    year = int(match.group(3)) if match.group(3) else datetime.now().year
                    
                    # Ищем месяц
                    month = None
                    for key, value in month_map.items():
                        if month_text.startswith(key):
                            month = value
                            break
                    
                    if month:
                        return datetime(year, month, day)
                else:  # Числовой формат
                    if pattern.startswith(r'(\d{4})'):  # YYYY-MM-DD
                        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    else:  # DD.MM.YYYY
                        day, month, year_raw = int(match.group(1)), int(match.group(2)), int(match.group(3))
                        year = 2000 + year_raw if year_raw < 100 else year_raw
                    
                    return datetime(year, month, day)
            except ValueError:
                continue
    
    # Пробуем английские паттерны
    for pattern, month_map in en_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                month_text = match.group(1).lower()
                day = int(match.group(2))
                year = int(match.group(3))
                
                month = month_map.get(month_text)
                if month:
                    return datetime(year, month, day)
            except ValueError:
                continue
    
    # Если ничего не найдено
    return None


# Псевдоним для совместимости
def parse(date_string: str, languages: list = None) -> Optional[datetime]:
    return parse_date(date_string, languages)