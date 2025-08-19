#!/usr/bin/env python3
"""
Тесты для веб-экстрактора контента
"""

import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from content_extraction.web_extractor import _extract_content, _normalize_text, _extract_links_from_html


def load_fixture(filename: str) -> str:
    """Загружает HTML фикстуру из файла"""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return f.read()


def test_news_extraction():
    """Тест извлечения контента из новостной статьи"""
    html = load_fixture("news.html")
    
    page = _extract_content("https://example.com/news", "https://example.com/news", html)
    
    # Проверяем, что извлечен достаточный объем текста
    assert len(page.text) >= 800, f"Извлечено только {len(page.text)} символов, ожидалось >= 800"
    
    # Проверяем заголовок
    assert page.title is not None, "Заголовок не извлечен"
    assert "революция" in page.title.lower() or "ии" in page.title.lower(), f"Неверный заголовок: {page.title}"
    
    # Проверяем ссылки
    assert len(page.links) >= 3, f"Найдено только {len(page.links)} ссылок, ожидалось >= 3"
    
    # Проверяем, что ссылки нормализованы
    for link in page.links:
        assert link['href'].startswith('https://'), f"Ненормализованная ссылка: {link['href']}"
        assert len(link['text']) > 3, f"Слишком короткий текст ссылки: {link['text']}"
    
    # Проверяем метаданные
    assert 'og:title' in page.meta or 'description' in page.meta, "Метаданные не извлечены"
    
    print(f"✅ News extraction: {len(page.text)} символов, {len(page.links)} ссылок")


def test_blog_extraction():
    """Тест извлечения контента из блога (fallback на readability)"""
    html = load_fixture("blog.html")
    
    page = _extract_content("https://example.com/blog", "https://example.com/blog", html)
    
    # Проверяем извлечение контента
    assert len(page.text) >= 500, f"Извлечено только {len(page.text)} символов, ожидалось >= 500"
    
    # Проверяем, что в тексте есть содержательная информация
    assert "python" in page.text.lower(), "Основная тема статьи не найдена в тексте"
    assert "программирование" in page.text.lower() or "разработчик" in page.text.lower(), "Ключевые слова не найдены"
    
    # Проверяем заголовок
    assert page.title is not None, "Заголовок не извлечен"
    
    print(f"✅ Blog extraction: {len(page.text)} символов")


def test_portal_with_noise():
    """Тест извлечения контента с портала с большим количеством мусора"""
    html = load_fixture("portal.html")
    
    page = _extract_content("https://example.com/portal", "https://example.com/portal", html)
    
    # Проверяем, что извлечен основной контент
    assert len(page.text) >= 350, f"Извлечено только {len(page.text)} символов, ожидалось >= 350"
    
    # Проверяем, что мусор не попал в контент
    noise_words = ["реклама", "подписаться", "поделиться", "навигация", "погода"]
    text_lower = page.text.lower()
    
    for noise_word in noise_words:
        assert noise_word not in text_lower or text_lower.count(noise_word) <= 1, \
            f"Найден мусорный контент: {noise_word}"
    
    # Проверяем, что основной контент присутствует
    assert "технологи" in text_lower, "Основной контент не найден"
    assert "искусственный интеллект" in text_lower, "Ключевая информация не найдена"
    
    print(f"✅ Portal extraction: {len(page.text)} символов, мусор отфильтрован")


def test_short_content_error():
    """Тест обработки короткого контента"""
    html = load_fixture("short.html")
    
    try:
        page = _extract_content("https://example.com/short", "https://example.com/short", html)
        # Если извлечение прошло, проверяем что контент действительно короткий
        assert len(page.text) < 350, "Короткий контент не должен проходить минимальный порог"
    except Exception as e:
        # Ожидаем ошибку о коротком контенте
        assert "не удалось извлечь" in str(e).lower(), f"Неожиданная ошибка: {e}"
        print("✅ Short content correctly rejected")
        return
    
    print("⚠️ Short content was extracted, but it's very short")


def test_text_normalization():
    """Тест нормализации текста"""
    test_cases = [
        # Множественные пробелы
        ("Это   текст  с    большими     пробелами", "Это текст с большими пробелами"),
        
        # Неразрывные пробелы
        ("Текст\xa0с\xa0неразрывными\xa0пробелами", "Текст с неразрывными пробелами"),
        
        # Множественные переводы строк
        ("Абзац 1\n\n\n\nАбзац 2", "Абзац 1\n\nАбзац 2"),
        
        # Пустой текст
        ("", ""),
        
        # Только пробелы
        ("   \n\n   ", ""),
    ]
    
    for input_text, expected in test_cases:
        result = _normalize_text(input_text)
        assert result == expected, f"Нормализация не удалась. Вход: {repr(input_text)}, ожидалось: {repr(expected)}, получено: {repr(result)}"
    
    print("✅ Text normalization works correctly")


def test_link_normalization():
    """Тест нормализации ссылок"""
    html = """
    <html>
    <body>
        <a href="https://example.com/full">Полная ссылка</a>
        <a href="/relative">Относительная ссылка</a>
        <a href="#anchor">Якорь</a>
        <a href="mailto:test@example.com">Email</a>
        <a href="tel:+123456789">Телефон</a>
        <a href="javascript:void(0)">JavaScript</a>
        <a href="http://another.com/path">Другой домен</a>
        <a href="/short" title="Короткий заголовок">OK</a>
        <a href="/empty"></a>
    </body>
    </html>
    """
    
    links = _extract_links_from_html(html, "https://example.com/page")
    
    # Проверяем количество валидных ссылок
    assert len(links) >= 3, f"Найдено только {len(links)} валидных ссылок"
    
    # Проверяем нормализацию
    relative_link = next((link for link in links if "relative" in link['href']), None)
    assert relative_link is not None, "Относительная ссылка не найдена"
    assert relative_link['href'] == "https://example.com/relative", f"Неверная нормализация: {relative_link['href']}"
    
    # Проверяем фильтрацию якорей, mailto, tel
    for link in links:
        assert not link['href'].startswith('#'), "Якорь не отфильтрован"
        assert not link['href'].startswith('mailto:'), "Email не отфильтрован"
        assert not link['href'].startswith('tel:'), "Телефон не отфильтрован"
        assert not link['href'].startswith('javascript:'), "JavaScript не отфильтрован"
        assert len(link['text']) > 3, f"Слишком короткий текст ссылки: {link['text']}"
    
    print(f"✅ Link normalization: {len(links)} валидных ссылок")


def run_all_tests():
    """Запускает все тесты"""
    tests = [
        test_news_extraction,
        test_blog_extraction,
        test_portal_with_noise,
        test_short_content_error,
        test_text_normalization,
        test_link_normalization
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
    
    print(f"\n📊 Результаты тестов: {passed} прошли, {failed} провалились")
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)