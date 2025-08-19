"""
PDF экстрактор с OCR поддержкой
Сначала пробует текстовый слой PyMuPDF, затем OCR через Tesseract
"""

import logging
import os
import shutil
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Проверяем наличие зависимостей
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF не установлен - PDF обработка недоступна")

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
except ImportError:
    TESSERACT_AVAILABLE = False

if not TESSERACT_AVAILABLE:
    logger.warning("Tesseract OCR не найден - OCR функции недоступны")


def extract_text_from_pdf(path: str, ocr_langs: str = "rus+eng",
                          dpi: int = 200, max_pages_ocr: int = 50,
                          min_text_chars_per_page: int = 40) -> Dict[str, Any]:
    """
    Извлекает текст из PDF с автоматическим OCR для сканов.
    
    Args:
        path: путь к PDF файлу
        ocr_langs: языки для OCR (например "rus+eng")
        dpi: разрешение для рендеринга страниц в OCR
        max_pages_ocr: максимальное количество страниц для OCR
        min_text_chars_per_page: минимум символов на странице для считания "текстовой"
    
    Returns:
        Dict с полями: success, text, method, meta, error
    """
    
    if not PYMUPDF_AVAILABLE:
        return {
            "success": False, 
            "error": "PyMuPDF не установлен - установите пакет pymupdf"
        }
    
    try:
        doc = fitz.open(path)
    except Exception as e:
        logger.error(f"Ошибка открытия PDF {path}: {e}")
        return {"success": False, "error": f"Не удалось открыть PDF: {e}"}

    pages = doc.page_count
    text_chunks: List[str] = []
    ocr_pages: List[int] = []
    used_ocr = False
    
    logger.info(f"Обрабатываю PDF: {pages} страниц, макс. OCR: {max_pages_ocr}")

    for i in range(pages):
        try:
            page = doc.load_page(i)
            page_text = page.get_text("text") or ""
            page_text = page_text.strip()

            if len(page_text) >= min_text_chars_per_page:
                # Достаточно текста на странице - используем его
                text_chunks.append(page_text)
                logger.debug(f"Страница {i+1}: извлечен текстовый слой ({len(page_text)} символов)")
                continue

            # Мало текста - пробуем OCR
            if not TESSERACT_AVAILABLE:
                logger.warning(f"Страница {i+1}: мало текста ({len(page_text)} символов), но OCR недоступен")
                if page_text:  # Берем то что есть
                    text_chunks.append(page_text)
                continue
                
            if i >= max_pages_ocr:
                logger.info(f"Страница {i+1}: пропущен OCR - достигнут лимит {max_pages_ocr}")
                if page_text:  # Берем то что есть
                    text_chunks.append(page_text)
                continue

            # Выполняем OCR
            try:
                logger.debug(f"Страница {i+1}: выполняю OCR с разрешением {dpi} DPI")
                
                # Рендерим страницу в изображение
                matrix = fitz.Matrix(dpi/72, dpi/72)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # OCR с настройками для документов
                ocr_text = pytesseract.image_to_string(
                    img, 
                    lang=ocr_langs, 
                    config="--psm 6 -c tessedit_char_whitelist=АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюяABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?:;()[]{}\"'- \n"
                )
                ocr_text = (ocr_text or "").strip()
                
                if ocr_text and len(ocr_text) > 10:  # Минимальная проверка качества OCR
                    text_chunks.append(ocr_text)
                    ocr_pages.append(i + 1)
                    used_ocr = True
                    logger.info(f"Страница {i+1}: OCR извлек {len(ocr_text)} символов")
                else:
                    logger.warning(f"Страница {i+1}: OCR не дал полезного результата")
                    if page_text:  # Берем исходный текст, если он есть
                        text_chunks.append(page_text)
                        
            except Exception as ocr_err:
                logger.error(f"OCR ошибка на странице {i+1}: {ocr_err}")
                if page_text:  # Fallback на исходный текст
                    text_chunks.append(page_text)
                    
        except Exception as page_err:
            logger.error(f"Ошибка обработки страницы {i+1}: {page_err}")
            continue

    doc.close()
    
    # Объединяем весь извлеченный текст
    full_text = "\n\n".join(text_chunks).strip()
    
    if not full_text:
        return {
            "success": False, 
            "error": "PDF не содержит извлекаемого текста и OCR не дал результата"
        }

    # Нормализация текста
    full_text = _normalize_extracted_text(full_text)
    
    method = f"pymupdf+{'ocr' if used_ocr else 'text'}"
    
    logger.info(f"PDF обработан: {len(full_text)} символов, метод: {method}")
    
    return {
        "success": True,
        "text": full_text,
        "method": method,
        "meta": {
            "pages": pages,
            "ocr_pages": ocr_pages,
            "total_ocr_pages": len(ocr_pages),
            "text_extraction_stats": f"{len(text_chunks)} блоков текста"
        }
    }


def _normalize_extracted_text(text: str) -> str:
    """Нормализует извлеченный текст"""
    import re
    
    # Убираем лишние пробелы и переводы строк
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    # Убираем артефакты OCR
    text = re.sub(r'[^\w\s\n.,!?:;()[\]{}"\'-]', '', text)
    
    # Разбиваем длинные строки
    lines = text.split('\n')
    normalized_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Разбиваем слишком длинные строки
        if len(line) > 1000:
            words = line.split()
            current_line = ""
            for word in words:
                if len(current_line + " " + word) > 800:
                    if current_line:
                        normalized_lines.append(current_line.strip())
                    current_line = word
                else:
                    current_line += " " + word if current_line else word
            if current_line:
                normalized_lines.append(current_line.strip())
        else:
            normalized_lines.append(line)
    
    return '\n\n'.join(normalized_lines).strip()


def check_ocr_availability() -> Dict[str, bool]:
    """Проверяет доступность OCR компонентов"""
    return {
        "pymupdf": PYMUPDF_AVAILABLE,
        "tesseract": TESSERACT_AVAILABLE,
        "pillow": True  # Pillow всегда доступен при успешном импорте
    }


def get_ocr_info() -> str:
    """Возвращает информацию о доступных OCR компонентах"""
    availability = check_ocr_availability()
    
    if all(availability.values()):
        return "PDF + OCR полностью поддерживается"
    elif availability["pymupdf"]:
        return "PDF поддерживается (только текстовый слой, OCR недоступен)"
    else:
        return "PDF обработка недоступна - установите pymupdf"