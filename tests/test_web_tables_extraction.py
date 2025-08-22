"""
Тесты извлечения таблиц из веб-страниц в Markdown формате
"""

import pytest
from content_extraction.web_extractor import extract_tables_as_markdown
from quality.quality_checks import extract_critical_numbers

# HTML с таблицами для тестирования
SAMPLE_HTML_WITH_TABLE = """
<!DOCTYPE html>
<html>
<head><title>Финансовые результаты</title></head>
<body>
    <h1>Квартальные результаты</h1>
    <p>Компания представляет финансовые показатели за Q3 2024:</p>
    
    <table border="1">
        <thead>
            <tr>
                <th>Показатель</th>
                <th>Q2 2024</th>
                <th>Q3 2024</th>
                <th>Изменение</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Выручка (млрд ₽)</td>
                <td>2,8</td>
                <td>3,2</td>
                <td>+14,3%</td>
            </tr>
            <tr>
                <td>EBITDA (млрд ₽)</td>
                <td>0,84</td>
                <td>1,12</td>
                <td>+33,3%</td>
            </tr>
            <tr>
                <td>Чистая прибыль (млн ₽)</td>
                <td>420</td>
                <td>580</td>
                <td>+38,1%</td>
            </tr>
        </tbody>
    </table>
    
    <p>Результаты превзошли ожидания аналитиков.</p>
</body>
</html>
"""

COMPLEX_HTML_WITH_MULTIPLE_TABLES = """
<!DOCTYPE html>
<html>
<body>
    <h1>Аналитический отчет</h1>
    
    <!-- Первая таблица: Финансы -->
    <h2>Финансовые показатели</h2>
    <table>
        <tr>
            <th>Метрика</th>
            <th>Значение</th>
            <th>Валюта</th>
        </tr>
        <tr>
            <td>Выручка</td>
            <td>1,5</td>
            <td>млрд $</td>
        </tr>
        <tr>
            <td>Расходы</td>
            <td>950</td>
            <td>млн $</td>
        </tr>
    </table>
    
    <!-- Вторая таблица: Операционные данные -->
    <h2>Операционные данные</h2>
    <table>
        <thead>
            <tr><th>Регион</th><th>Продажи (тыс. ед.)</th><th>Доля рынка</th></tr>
        </thead>
        <tbody>
            <tr><td>Москва</td><td>125</td><td>23,5%</td></tr>
            <tr><td>СПб</td><td>89</td><td>18,2%</td></tr>
            <tr><td>Регионы</td><td>234</td><td>45,8%</td></tr>
        </tbody>
    </table>
    
    <!-- Некорректная таблица (должна игнорироваться) -->
    <table>
        <tr><td></td><td></td></tr>
        <tr><td></td></tr>
    </table>
    
</body>
</html>
"""

MALFORMED_HTML_TABLE = """
<html><body>
<table>
    <tr><td>Битая таблица<td>без закрывающих тегов
    <tr><td>Вторая строка<td>также битая
</table>
</body></html>
"""

def test_single_table_extraction():
    """Тест извлечения одной таблицы в Markdown"""
    
    markdown = extract_tables_as_markdown(SAMPLE_HTML_WITH_TABLE)
    
    assert markdown != "", "Таблица должна быть извлечена"
    assert "| Показатель | Q2 2024 | Q3 2024 | Изменение |" in markdown
    assert "| --- | --- | --- | --- |" in markdown  # Разделитель заголовков
    assert "| Выручка (млрд ₽) | 2,8 | 3,2 | +14,3% |" in markdown
    assert "| EBITDA (млрд ₽) | 0,84 | 1,12 | +33,3% |" in markdown
    assert "Таблица:" in markdown or "Таблица 1:" in markdown
    
    print("Извлеченная таблица:")
    print(markdown)

def test_multiple_tables_extraction():
    """Тест извлечения нескольких таблиц"""
    
    markdown = extract_tables_as_markdown(COMPLEX_HTML_WITH_MULTIPLE_TABLES)
    
    assert markdown != "", "Таблицы должны быть извлечены"
    
    # Проверяем наличие обеих таблиц
    assert "Выручка" in markdown and "1,5" in markdown  # Первая таблица
    assert "Москва" in markdown and "23,5%" in markdown  # Вторая таблица
    
    # Проверяем что есть разделители между таблицами
    table_count = markdown.count("Таблица")
    assert table_count >= 2, f"Должно быть минимум 2 таблицы, найдено: {table_count}"
    
    print("Извлеченные таблицы:")
    print(markdown)

def test_numbers_preserved_in_tables():
    """Тест сохранности чисел при извлечении таблиц"""
    
    markdown = extract_tables_as_markdown(SAMPLE_HTML_WITH_TABLE)
    
    # Извлекаем числа из оригинального HTML и Markdown
    original_numbers = extract_critical_numbers(SAMPLE_HTML_WITH_TABLE)
    markdown_numbers = extract_critical_numbers(markdown)
    
    # Ключевые числа из таблицы
    key_numbers = ['2,8', '3,2', '14,3%', '0,84', '1,12', '33,3%', '420', '580', '38,1%']
    
    preserved_count = 0
    for number in key_numbers:
        if any(number in md_num for md_num in markdown_numbers):
            preserved_count += 1
            print(f"✓ Число {number} сохранено в Markdown")
        else:
            print(f"✗ Число {number} потеряно")
    
    # Должно быть сохранено минимум 80% чисел
    preservation_rate = preserved_count / len(key_numbers)
    assert preservation_rate >= 0.8, f"Сохранность чисел в таблицах: {preservation_rate:.1%}"

def test_malformed_html_handling():
    """Тест обработки битого HTML"""
    
    # Не должно падать с ошибкой
    markdown = extract_tables_as_markdown(MALFORMED_HTML_TABLE)
    
    # Может быть пустым или содержать частично извлеченные данные
    print(f"Результат для битого HTML: {repr(markdown)}")
    
    # Главное - не должно быть исключения

def test_empty_html_handling():
    """Тест обработки пустого/некорректного HTML"""
    
    empty_cases = [
        "",  # Пустая строка
        "<html></html>",  # HTML без таблиц
        "<p>Текст без таблиц</p>",  # Контент без таблиц
        "<table></table>",  # Пустая таблица
        "<table><tr></tr></table>",  # Таблица с пустыми строками
    ]
    
    for html in empty_cases:
        markdown = extract_tables_as_markdown(html)
        # Должно возвращать пустую строку, а не падать
        assert isinstance(markdown, str), f"Должна возвращаться строка для: {html}"
        print(f"Результат для '{html[:30]}...': {repr(markdown[:50])}")

def test_large_table_limits():
    """Тест ограничений на размер таблиц"""
    
    # Создаем большую таблицу (30 строк, 5 колонок)
    large_table_html = """
    <table>
        <tr><th>Col1</th><th>Col2</th><th>Col3</th><th>Col4</th><th>Col5</th></tr>
    """
    
    for i in range(30):
        large_table_html += f"<tr><td>Row{i}</td><td>{i*10}%</td><td>${i*100}</td><td>Data{i}</td><td>Value{i}</td></tr>"
    
    large_table_html += "</table>"
    
    markdown = extract_tables_as_markdown(large_table_html)
    
    # Проверяем что таблица обрезана (не более 20 строк данных)
    lines = markdown.split('\n')
    data_lines = [line for line in lines if line.startswith('| Row')]
    
    assert len(data_lines) <= 20, f"Таблица должна быть ограничена 20 строками, найдено: {len(data_lines)}"

def test_table_formatting_edge_cases():
    """Тест граничных случаев форматирования таблиц"""
    
    edge_case_html = """
    <table>
        <tr>
            <th>Заголовок с | символом</th>
            <th>Пустой заголовок</th>
            <th></th>
        </tr>
        <tr>
            <td>Ячейка с
            переносом строки</td>
            <td>   Лишние пробелы   </td>
            <td></td>
        </tr>
        <tr>
            <td>Ячейка с <b>HTML</b> тегами</td>
            <td>Спецсимволы: & < > "</td>
            <td>25,5%</td>
        </tr>
    </table>
    """
    
    markdown = extract_tables_as_markdown(edge_case_html)
    
    assert markdown != "", "Таблица должна быть обработана"
    
    # Проверяем что HTML теги удалены
    assert "<b>" not in markdown and "</b>" not in markdown
    
    # Проверяем что переносы строк обработаны
    assert "Ячейка с переносом строки" in markdown or "переносом" in markdown
    
    # Проверяем что числа сохранились
    assert "25,5%" in markdown
    
    print("Результат для граничных случаев:")
    print(markdown)

if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"])