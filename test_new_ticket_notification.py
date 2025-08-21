#!/usr/bin/env python3
"""
Тестирование уведомления о новом тикете
"""

import requests
import json

INTERNAL_NOTIFY_URL = "http://localhost:8080/internal/notify"

def test_new_ticket_notification():
    """Тест уведомления о новом тикете"""
    print("🆕 Тестируем уведомление о НОВОМ ТИКЕТЕ...")
    
    data = {
        "type": "new_ticket",
        "ticket_id": "999"
    }
    
    print(f"Отправляем данные: {data}")
    print(f"URL: {INTERNAL_NOTIFY_URL}")
    
    try:
        response = requests.post(INTERNAL_NOTIFY_URL, json=data, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
        
        if response.status_code == 204:
            print("✅ Уведомление о новом тикете отправлено успешно")
        else:
            print("❌ Ошибка при отправке уведомления о новом тикете")
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")

if __name__ == "__main__":
    test_new_ticket_notification()
