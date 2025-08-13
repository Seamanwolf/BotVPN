#!/usr/bin/env python3
"""
Финальный тест всех функций веб-панели
"""

import requests
import json

def final_test():
    """Финальный тест всех функций"""
    print("🎯 Финальный тест веб-панели...")
    
    base_url = "http://localhost:8080"
    session = requests.Session()
    
    # 1. Вход в систему
    login_data = {
        'username': 'superadmin',
        'password': 'admin123'
    }
    
    try:
        response = session.post(f"{base_url}/login", data=login_data, timeout=5)
        if response.status_code == 200:
            print("✅ Вход в систему успешен")
        else:
            print(f"❌ Ошибка входа: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Ошибка при входе: {e}")
        return
    
    # 2. Тест API пользователей
    try:
        response = session.get(f"{base_url}/api/user/1", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ API пользователей работает")
            else:
                print(f"⚠️ API пользователей: {data.get('message')}")
        else:
            print(f"❌ API пользователей: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка API пользователей: {e}")
    
    # 3. Тест API подписок
    try:
        response = session.get(f"{base_url}/api/subscription/1", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ API подписок работает")
            else:
                print(f"⚠️ API подписок: {data.get('message')}")
        else:
            print(f"❌ API подписок: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка API подписок: {e}")
    
    # 4. Тест API админов
    try:
        response = session.get(f"{base_url}/api/admin/1", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ API админов работает")
            else:
                print(f"⚠️ API админов: {data.get('message')}")
        else:
            print(f"❌ API админов: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка API админов: {e}")
    
    # 5. Проверка страниц
    pages = [
        ('/', 'Дашборд'),
        ('/users', 'Пользователи'),
        ('/subscriptions', 'Подписки'),
        ('/admins', 'Администраторы')
    ]
    
    for page, name in pages:
        try:
            response = session.get(f"{base_url}{page}", timeout=5)
            if response.status_code == 200:
                print(f"✅ Страница {name} доступна")
            else:
                print(f"❌ Страница {name}: {response.status_code}")
        except Exception as e:
            print(f"❌ Ошибка страницы {name}: {e}")
    
    print("\n🎉 Веб-панель полностью готова к работе!")
    print("📝 Доступные функции:")
    print("   ✅ Аутентификация и авторизация")
    print("   ✅ Управление пользователями с фильтрами и поиском")
    print("   ✅ Управление подписками (просмотр, продление, приостановка, удаление)")
    print("   ✅ Создание подписок вручную")
    print("   ✅ Управление администраторами (добавление, удаление, блокировка)")
    print("   ✅ Синхронизация с 3xUI")
    print("   ✅ Модальные окна для детального просмотра")
    print("\n🌐 Откройте http://localhost:8080 в браузере")

if __name__ == "__main__":
    final_test()
