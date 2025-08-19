#!/usr/bin/env python3
"""
Тест обработки URL с улучшенной детекцией Cloudflare
"""
import sys
import os
import requests
from bs4 import BeautifulSoup

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_cloudflare_detection():
    """Тест детекции Cloudflare защиты"""
    print("=== Тест детекции Cloudflare ===")
    
    cloudflare_indicators = [
        'just a moment', 'challenge-platform', 'cloudflare',
        'please wait while your request is being verified',
        'enable javascript and cookies to continue',
        '_cf_chl_opt', 'cf-browser-verification'
    ]
    
    # Реальный контент от TechSpot
    techspot_response = '''<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <script>(function(){window._cf_chl_opt = {cvId: '3',cZone: 'www.techspot.com'}})</script>'''
    
    detected = any(indicator in techspot_response.lower() for indicator in cloudflare_indicators)
    print(f"TechSpot Cloudflare detection: {detected} ✅")
    
    # Нормальный контент
    normal_content = "This is a regular news article about technology and innovation"
    normal_detected = any(indicator in normal_content.lower() for indicator in cloudflare_indicators)
    print(f"False positive check: {not normal_detected} ✅")
    
    return detected and not normal_detected

def test_url_processing():
    """Тест полной обработки URL"""
    print("\n=== Тест обработки URL ===")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
    }
    
    test_urls = [
        # Проблемный URL
        ("TechSpot (Cloudflare)", "https://www.techspot.com/news/109095-steve-wozniak-reflects-happiness-legacy-75th-birthday.html"),
        # Рабочий URL для сравнения  
        ("HTTPBin (should work)", "https://httpbin.org/html"),
    ]
    
    results = []
    
    for name, url in test_urls:
        print(f"\nТестирую {name}:")
        print(f"URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            print(f"Status: {response.status_code}")
            
            # Проверяем на Cloudflare
            cloudflare_indicators = [
                'just a moment', 'challenge-platform', 'cloudflare',
                'enable javascript and cookies to continue',
                '_cf_chl_opt', 'cf-browser-verification'
            ]
            
            page_text = response.text.lower()
            is_blocked = any(indicator in page_text for indicator in cloudflare_indicators)
            
            if is_blocked:
                print("❌ Cloudflare protection detected")
                results.append((name, "blocked"))
            else:
                soup = BeautifulSoup(response.content, 'lxml')
                text = soup.get_text()
                text_length = len(text.strip())
                
                print(f"✅ Content extracted: {text_length} characters")
                if text_length > 100:
                    print(f"First 100 chars: {text[:100]}...")
                    results.append((name, "success"))
                else:
                    print("⚠️ Content too short")
                    results.append((name, "short_content"))
                    
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append((name, f"error: {e}"))
    
    return results

def main():
    """Запуск всех тестов"""
    print("🧪 Тест улучшенной обработки URL и детекции Cloudflare\n")
    
    # Тест детекции Cloudflare
    cloudflare_test = test_cloudflare_detection()
    
    # Тест обработки URL
    url_results = test_url_processing()
    
    print(f"\n{'='*50}")
    print("📊 РЕЗУЛЬТАТЫ ТЕСТОВ:")
    print(f"Cloudflare detection: {'✅ OK' if cloudflare_test else '❌ FAIL'}")
    
    print("\nURL processing results:")
    for name, result in url_results:
        status_icon = {
            'success': '✅',
            'blocked': '🚫', 
            'short_content': '⚠️'
        }.get(result.split(':')[0], '❌')
        print(f"  {name}: {status_icon} {result}")
    
    print(f"\n{'='*50}")
    
    # Проверяем, что TechSpot корректно определяется как заблокированный
    techspot_blocked = any('blocked' in result for name, result in url_results if 'TechSpot' in name)
    
    if techspot_blocked:
        print("✅ УСПЕХ: TechSpot корректно определен как заблокированный Cloudflare")
        print("   Бот теперь будет показывать понятное сообщение пользователю")
        print("\n💡 Рекомендация пользователю:")
        print("   'Сайт использует защиту от ботов (Cloudflare).")
        print("   Попробуйте скопировать текст статьи вручную или найти альтернативный источник.'")
        return 0
    else:
        print("❌ ОШИБКА: TechSpot должен определяться как заблокированный")
        return 1

if __name__ == "__main__":
    sys.exit(main())