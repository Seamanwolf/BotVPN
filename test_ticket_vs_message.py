#!/usr/bin/env python3
"""
Тестирование разницы между уведомлениями о новом тикете и новом сообщении
"""

import requests
import json
import time

INTERNAL_NOTIFY_URL = "http://localhost:8080/internal/notify"

def test_new_ticket():
    """Тест уведомления о новом тикете"""
    print("🆕 Тестируем уведомление о НОВОМ ТИКЕТЕ...")
    
    data = {
        "type": "new_ticket",
        "ticket_id": "999"
    }
    
    response = requests.post(INTERNAL_NOTIFY_URL, json=data)
    print(f"Статус: {response.status_code}")
    print(f"Ответ: {response.text}")
    
    if response.status_code == 204:
        print("✅ Уведомление о новом тикете отправлено успешно")
    else:
        print("❌ Ошибка при отправке уведомления о новом тикете")

def test_new_message():
    """Тест уведомления о новом сообщении"""
    print("\n💬 Тестируем уведомление о НОВОМ СООБЩЕНИИ...")
    
    data = {
        "ticket_id": "123",
        "message_id": "456",
        "preview": "Тестовое сообщение от пользователя",
        "author": "user"
    }
    
    response = requests.post(INTERNAL_NOTIFY_URL, json=data)
    print(f"Статус: {response.status_code}")
    print(f"Ответ: {response.text}")
    
    if response.status_code == 204:
        print("✅ Уведомление о новом сообщении отправлено успешно")
    else:
        print("❌ Ошибка при отправке уведомления о новом сообщении")

def test_new_user():
    """Тест уведомления о новом пользователе"""
    print("\n👤 Тестируем уведомление о НОВОМ ПОЛЬЗОВАТЕЛЕ...")
    
    data = {
        "type": "new_user",
        "user_id": "789",
        "full_name": "Тестовый Пользователь",
        "phone": "+1234567890",
        "email": "test@example.com"
    }
    
    response = requests.post(INTERNAL_NOTIFY_URL, json=data)
    print(f"Статус: {response.status_code}")
    print(f"Ответ: {response.text}")
    
    if response.status_code == 204:
        print("✅ Уведомление о новом пользователе отправлено успешно")
    else:
        print("❌ Ошибка при отправке уведомления о новом пользователе")

if __name__ == "__main__":
    print("=== ТЕСТИРОВАНИЕ РАЗЛИЧНЫХ ТИПОВ УВЕДОМЛЕНИЙ ===\n")
    
    test_new_ticket()
    time.sleep(2)  # Пауза между тестами
    
    test_new_message()
    time.sleep(2)  # Пауза между тестами
    
    test_new_user()
    
    print("\n=== РЕЗУЛЬТАТЫ ===")
    print("Теперь в веб-админке должны быть разные уведомления:")
    print("🆕 Новый тикет - должно показывать 'Новый тикет'")
    print("💬 Новое сообщение - должно показывать 'Новое сообщение'")
    print("👤 Новый пользователь - должно показывать 'Новый пользователь'")
