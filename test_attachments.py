#!/usr/bin/env python3

import requests
from database import SessionLocal, TicketMessage

def test_attachments():
    """Тестирует доступность вложений"""
    db = SessionLocal()
    try:
        # Получаем последние сообщения с вложениями
        messages = db.query(TicketMessage).filter(
            TicketMessage.attachment_url.isnot(None)
        ).limit(5).all()
        
        print(f"Найдено {len(messages)} сообщений с вложениями:")
        
        for msg in messages:
            print(f"\nСообщение ID: {msg.id}")
            print(f"Тип вложения: {msg.attachment_type}")
            print(f"URL: {msg.attachment_url}")
            
            # Проверяем доступность URL
            try:
                response = requests.head(msg.attachment_url, timeout=5)
                print(f"Статус: {response.status_code}")
                if response.status_code == 200:
                    print("✅ URL доступен")
                else:
                    print("❌ URL недоступен")
            except Exception as e:
                print(f"❌ Ошибка при проверке URL: {e}")
                
    finally:
        db.close()

if __name__ == "__main__":
    test_attachments()
