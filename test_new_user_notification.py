#!/usr/bin/env python3

import requests
import json

def test_new_user_notification():
    """Тестирует отправку уведомлений о новых пользователях"""
    
    url = "http://127.0.0.1:8080/internal/notify"
    data = {
        "type": "new_user",
        "user_id": "123",
        "full_name": "Тестовый Пользователь",
        "phone": "+79001234567",
        "email": "test@example.com"
    }
    
    print("Отправляем тестовое уведомление о новом пользователе...")
    print(f"URL: {url}")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
        
        if response.status_code == 204:
            print("✅ Уведомление о новом пользователе отправлено успешно!")
        else:
            print("❌ Ошибка при отправке уведомления")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_new_user_notification()
