#!/usr/bin/env python3

import requests
import json

def test_notification():
    """Тестирует отправку уведомлений"""
    
    url = "http://127.0.0.1:8080/internal/notify"
    data = {
        "ticket_id": "123",
        "message_id": "456",
        "preview": "Тестовое сообщение для проверки уведомлений",
        "author": "user"
    }
    
    print("Отправляем тестовое уведомление...")
    print(f"URL: {url}")
    print(f"Data: {json.dumps(data, indent=2)}")
    
    try:
        response = requests.post(url, json=data, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
        
        if response.status_code == 204:
            print("✅ Уведомление отправлено успешно!")
        else:
            print("❌ Ошибка при отправке уведомления")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_notification()
