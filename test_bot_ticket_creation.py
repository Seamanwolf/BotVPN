#!/usr/bin/env python3
"""
Тест создания тикета через бота
"""

import requests
import json

def test_bot_ticket_creation():
    """Тестируем создание тикета через бота"""
    
    # URL для создания тикета (эмулируем запрос бота)
    url = "http://localhost:8080/internal/notify"
    
    # Данные для нового тикета
    data = {
        "type": "new_ticket",
        "ticket_id": "999"
    }
    
    print("🆕 Тестируем создание тикета через бота...")
    print(f"Отправляем данные: {data}")
    print(f"URL: {url}")
    
    try:
        response = requests.post(url, json=data, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
        
        if response.status_code == 204:
            print("✅ Уведомление о новом тикете отправлено успешно")
        else:
            print("❌ Ошибка при отправке уведомления")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_bot_ticket_creation()
