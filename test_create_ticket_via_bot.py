#!/usr/bin/env python3
"""
Тест создания тикета через бота
"""

import requests
import json
import time

def test_create_ticket_via_bot():
    """Тестируем создание тикета через бота"""
    
    print("🆕 Тестируем создание тикета через бота...")
    
    # Эмулируем создание тикета через бота
    # Сначала создаем тикет в базе данных
    from database import SessionLocal, Ticket, User, TicketMessage
    from datetime import datetime
    
    db = SessionLocal()
    try:
        # Находим первого пользователя
        user = db.query(User).first()
        if not user:
            print("❌ Нет пользователей в базе данных")
            return
        
        # Создаем тестовый тикет
        ticket = Ticket(
            ticket_number="TEST001",
            user_id=user.id,
            status="open",
            ticket_type="support",
            subject="Тестовый тикет"
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        
        print(f"✅ Тикет создан с ID: {ticket.id}")
        
        # Создаем первое сообщение в тикете
        message = TicketMessage(
            ticket_id=ticket.id,
            sender_id=user.id,
            sender_type="user",
            message="Тестовое сообщение"
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        
        print(f"✅ Сообщение создано с ID: {message.id}")
        
        # Теперь вызываем notify_new_ticket
        from notifications import notify_new_ticket
        
        print(f"📤 Отправляем уведомление о новом тикете {ticket.id}")
        notify_new_ticket(str(ticket.id))
        
        print("✅ Уведомление отправлено")
        
        # Ждем немного и проверяем логи
        time.sleep(2)
        
        # Проверяем, что уведомление дошло до веб-сервиса
        response = requests.get("http://localhost:8080/api/notifications/tickets-count")
        print(f"Статус проверки: {response.status_code}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_create_ticket_via_bot()
