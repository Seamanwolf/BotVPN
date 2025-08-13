#!/usr/bin/env python3

from database import SessionLocal, User
from xui_client import XUIClient
import asyncio

async def debug_email():
    # Проверяем пользователя в БД
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == 7107555507).first()
        if user:
            print(f"Пользователь в БД:")
            print(f"  ID: {user.id}")
            print(f"  Email: {user.email}")
            print(f"  Name: {user.full_name}")
            print(f"  Telegram ID: {user.telegram_id}")
        else:
            print("Пользователь не найден в БД")
            return
    finally:
        db.close()
    
    # Проверяем 3xUI
    try:
        xui_client = XUIClient()
        await xui_client.ensure_login()
        
        # Получаем конфигурацию с правильным email
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        print(f"\nПроверяем 3xUI с email: {user_email}")
        
        config = await xui_client.get_user_config(user_email)
        if config:
            print(f"✅ Конфигурация найдена в 3xUI")
        else:
            print(f"❌ Конфигурация не найдена в 3xUI")
            
        # Попробуем создать пользователя
        print(f"\nПробуем создать пользователя в 3xUI...")
        result = await xui_client.create_user(user_email, 1, f"TG: {user.telegram_id} {user.full_name}", str(user.telegram_id))
        print(f"Результат создания: {result}")
        
    except Exception as e:
        print(f"Ошибка при работе с 3xUI: {e}")

if __name__ == "__main__":
    asyncio.run(debug_email())
