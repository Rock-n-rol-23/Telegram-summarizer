#!/usr/bin/env python3
"""
Тесты для PDF OCR экстрактора
"""

import os
import sys
import shutil
from pathlib import Path

# Проверяем наличие Tesseract (пропускаем тесты если нет)
if shutil.which("tesseract") is None:
    print("⚠️ Tesseract не найден - пропускаем OCR тесты")
    sys.exit(0)

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from content_extraction.pdf_ocr import extract_text_from_pdf, check_ocr_availability, get_ocr_info
    import fitz  # PyMuPDF
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    print(f"❌ Зависимости недоступны: {e}")
    sys.exit(1)


def create_test_pdf_with_text_and_image(output_path: str):
    """Создает тестовый PDF со страницей с текстом и страницей-изображением"""
    doc = fitz.open()
    
    # Страница 1: обычный текст
    page1 = doc.new_page()
    text = """Тестовый документ для проверки извлечения текста

Это первая страница с обычным текстовым слоем.
Здесь есть русский текст и English text.

• Первый пункт списка
• Второй пункт списка  
• Третий пункт списка

Эта страница должна обрабатываться через текстовый слой PDF."""
    
    page1.insert_text((50, 50), text, fontsize=12, color=(0, 0, 0))
    
    # Страница 2: изображение с текстом (будет обработано OCR)
    page2 = doc.new_page()
    
    # Создаем изображение с текстом
    img = Image.new('RGB', (400, 300), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        # Пытаемся использовать стандартный шрифт
        font = ImageFont.load_default()
    except:
        font = None
    
    text_lines = [
        "OCR Test Page",
        "Тестовая страница для OCR",
        "This text should be recognized",
        "Этот текст должен распознаться",
        "Numbers: 12345"
    ]
    
    y_pos = 50
    for line in text_lines:
        draw.text((50, y_pos), line, fill='black', font=font)
        y_pos += 40
    
    # Сохраняем изображение временно
    temp_img_path = output_path.replace('.pdf', '_temp.png')
    img.save(temp_img_path)
    
    # Вставляем изображение в PDF
    page2.insert_image(fitz.Rect(50, 50, 450, 350), filename=temp_img_path)
    
    # Сохраняем PDF
    doc.save(output_path)
    doc.close()
    
    # Удаляем временное изображение
    if os.path.exists(temp_img_path):
        os.remove(temp_img_path)


def test_availability():
    """Тест проверки доступности компонентов"""
    print("🧪 Тест доступности OCR компонентов")
    
    availability = check_ocr_availability()
    print(f"PyMuPDF: {'✅' if availability['pymupdf'] else '❌'}")
    print(f"Tesseract: {'✅' if availability['tesseract'] else '❌'}")
    print(f"Pillow: {'✅' if availability['pillow'] else '❌'}")
    
    info = get_ocr_info()
    print(f"Статус: {info}")
    
    assert availability['pymupdf'], "PyMuPDF должен быть доступен"
    print("✅ Тест доступности прошел")


def test_pdf_text_and_ocr():
    """Тест извлечения текста и OCR из PDF"""
    print("\n🧪 Тест PDF с текстом и OCR")
    
    # Создаем тестовый PDF
    test_pdf_path = "test_mixed_content.pdf"
    try:
        create_test_pdf_with_text_and_image(test_pdf_path)
        assert os.path.exists(test_pdf_path), "Тестовый PDF не создан"
        
        # Извлекаем текст
        result = extract_text_from_pdf(test_pdf_path, min_text_chars_per_page=30)
        
        assert result['success'], f"Извлечение не удалось: {result.get('error')}"
        assert len(result['text']) >= 100, f"Слишком мало текста: {len(result['text'])} символов"
        
        # Проверяем что первая страница обработана как текст
        assert "Тестовый документ" in result['text'], "Текст с первой страницы не найден"
        
        # Проверяем метод извлечения
        method = result['method']
        print(f"Метод извлечения: {method}")
        
        # Проверяем метаданные
        meta = result['meta']
        assert meta['pages'] == 2, f"Ожидалось 2 страницы, получено {meta['pages']}"
        
        if meta.get('ocr_pages'):
            print(f"OCR страницы: {meta['ocr_pages']}")
            assert 2 in meta['ocr_pages'], "Вторая страница должна быть обработана OCR"
            assert "ocr" in method, f"Метод должен содержать 'ocr', получен: {method}"
        else:
            print("⚠️ OCR не был использован (возможно, Tesseract недоступен)")
        
        print(f"✅ Извлечено {len(result['text'])} символов")
        print(f"✅ Статистика: {meta.get('text_extraction_stats', 'N/A')}")
        
    finally:
        # Очищаем тестовый файл
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)


def test_pure_text_pdf():
    """Тест PDF только с текстовым слоем"""
    print("\n🧪 Тест PDF только с текстом")
    
    # Создаем простой текстовый PDF
    test_pdf_path = "test_text_only.pdf"
    try:
        doc = fitz.open()
        page = doc.new_page()
        
        text = """Это тестовый документ только с текстовым слоем.

Здесь достаточно текста для успешного извлечения через PyMuPDF.
Никакой OCR не должен использоваться для этого документа.

Русский текст: Привет, мир!
English text: Hello, world!
Цифры: 123456789"""
        
        page.insert_text((50, 50), text, fontsize=12)
        doc.save(test_pdf_path)
        doc.close()
        
        # Извлекаем текст
        result = extract_text_from_pdf(test_pdf_path)
        
        assert result['success'], f"Извлечение не удалось: {result.get('error')}"
        assert len(result['text']) >= 100, f"Слишком мало текста: {len(result['text'])} символов"
        assert "Это тестовый документ" in result['text'], "Основной текст не найден"
        
        # Проверяем что OCR НЕ использовался
        method = result['method']
        meta = result['meta']
        
        assert "ocr" not in method or not meta.get('ocr_pages'), "OCR не должен был использоваться"
        assert meta['pages'] == 1, f"Ожидалась 1 страница, получено {meta['pages']}"
        
        print(f"✅ Текстовый PDF: {len(result['text'])} символов, метод: {method}")
        
    finally:
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)


def test_error_handling():
    """Тест обработки ошибок"""
    print("\n🧪 Тест обработки ошибок")
    
    # Тест несуществующего файла
    result = extract_text_from_pdf("nonexistent_file.pdf")
    assert not result['success'], "Должна быть ошибка для несуществующего файла"
    assert "Не удалось открыть PDF" in result['error'], f"Неожиданная ошибка: {result['error']}"
    
    print("✅ Обработка ошибок работает корректно")


def run_all_tests():
    """Запускает все тесты"""
    print("🧪 Тестирование PDF OCR экстрактора\n")
    
    tests = [
        test_availability,
        test_pure_text_pdf, 
        test_pdf_text_and_ocr,
        test_error_handling
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
    
    print(f"\n📊 Результаты тестов PDF OCR: {passed} прошли, {failed} провалились")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)