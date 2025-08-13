#!/usr/bin/env python3
"""
Скрипт для тестирования веб-панели
"""

import requests
import json

def test_web_panel():
    """Тестирование веб-панели"""
    print("🧪 Тестируем веб-панель...")
    
    base_url = "http://localhost:8080"
    
    # Тест 1: Проверка доступности
    try:
        response = requests.get(f"{base_url}/login", timeout=5)
        if response.status_code == 200:
            print("✅ Страница входа доступна")
        else:
            print(f"❌ Страница входа недоступна: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка при проверке страницы входа: {e}")
        return
    
    # Тест 2: Проверка API админов (должен вернуть 302 - редирект на логин)
    try:
        response = requests.get(f"{base_url}/admins", timeout=5)
        if response.status_code == 302:
            print("✅ API админов защищен (требует авторизацию)")
        else:
            print(f"⚠️ API админов вернул: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка при проверке API админов: {e}")
    
    # Тест 3: Проверка API пользователей
    try:
        response = requests.get(f"{base_url}/users", timeout=5)
        if response.status_code == 302:
            print("✅ API пользователей защищен (требует авторизацию)")
        else:
            print(f"⚠️ API пользователей вернул: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка при проверке API пользователей: {e}")
    
    # Тест 4: Проверка API подписок
    try:
        response = requests.get(f"{base_url}/subscriptions", timeout=5)
        if response.status_code == 302:
            print("✅ API подписок защищен (требует авторизацию)")
        else:
            print(f"⚠️ API подписок вернул: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка при проверке API подписок: {e}")
    
    print("\n🎯 Веб-панель готова к использованию!")
    print("📝 Для входа используйте:")
    print("   URL: http://localhost:8080")
    print("   Логин: superadmin")
    print("   Пароль: admin123")

if __name__ == "__main__":
    test_web_panel()

