#!/usr/bin/env python3
"""
Скрипт проверки всех исправлений развертывания
"""
import requests
import sys
import json

def test_endpoint(url, expected_status=200):
    """Тестирование endpoint"""
    try:
        response = requests.get(url, timeout=5)
        print(f"✅ {url} → HTTP {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            data = response.json()
            print(f"   JSON: {json.dumps(data, indent=2)}")
        else:
            print(f"   Text: {response.text[:100]}")
            
        return response.status_code == expected_status
        
    except Exception as e:
        print(f"❌ {url} → Error: {e}")
        return False

def main():
    """Проверка всех исправлений"""
    base_url = "http://localhost:5000"
    
    print("=== ПРОВЕРКА ИСПРАВЛЕНИЙ РАЗВЕРТЫВАНИЯ ===\n")
    
    endpoints = [
        "/",
        "/health", 
        "/ready",
        "/status"
    ]
    
    all_passed = True
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        if not test_endpoint(url):
            all_passed = False
        print()
    
    if all_passed:
        print("🎉 ВСЕ ИСПРАВЛЕНИЯ ПРИМЕНЕНЫ УСПЕШНО!")
        print("✅ HTTP server отвечает на все endpoints")
        print("✅ Health checks работают") 
        print("✅ Готово к развертыванию на Cloud Run")
    else:
        print("❌ Есть проблемы с endpoints")
        sys.exit(1)

if __name__ == '__main__':
    main()