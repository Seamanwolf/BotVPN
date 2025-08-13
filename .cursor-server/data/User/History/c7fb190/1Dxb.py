#!/usr/bin/env python3
"""
Скрипт для тестирования аутентификации
"""

import requests
from werkzeug.security import check_password_hash

def test_auth():
    """Тестирование аутентификации"""
    print("🔐 Тестируем аутентификацию...")
    
    base_url = "http://localhost:8080"
    
    # Создаем сессию
    session = requests.Session()
    
    # Тест 1: Попытка входа с правильными данными
    login_data = {
        'username': 'superadmin',
        'password': 'admin123'
    }
    
    try:
        response = session.post(f"{base_url}/login", data=login_data, timeout=5)
        print(f"📝 Ответ на логин: {response.status_code}")
        
        if response.status_code == 302:
            print("✅ Логин успешен (редирект)")
        else:
            print(f"⚠️ Логин вернул: {response.status_code}")
            print(f"📄 Содержимое: {response.text[:200]}...")
    except Exception as e:
        print(f"❌ Ошибка при логине: {e}")
        return
    
    # Тест 2: Попытка доступа к защищенным страницам
    protected_pages = ['/admins', '/users', '/subscriptions']
    
    for page in protected_pages:
        try:
            response = session.get(f"{base_url}{page}", timeout=5)
            print(f"📄 {page}: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   ✅ Доступ разрешен")
            elif response.status_code == 302:
                print(f"   ⚠️ Редирект (возможно, не авторизован)")
            else:
                print(f"   ❌ Неожиданный код: {response.status_code}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")

if __name__ == "__main__":
    test_auth()

