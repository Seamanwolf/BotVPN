#!/usr/bin/env python3
"""
Скрипт для синхронизации статуса подписок с 3xUI
Просто обновляет статус active/expired в базе данных
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from database import SessionLocal, User, Subscription
from xui_client import XUIClient

async def sync_subscription_status():
    """Синхронизация статуса подписок с 3xUI"""
    
    print("🔍 Получение списка активных клиентов из 3xUI...")
    xui_client = XUIClient()
    await xui_client.login()
    inbounds = await xui_client.get_inbounds()
    
    # Собираем активные email из 3xUI
    active_emails = set()
    if inbounds and inbounds.get('obj'):
        for inbound in inbounds['obj']:
            settings_str = inbound.get('settings', '{}')
            try:
                settings = json.loads(settings_str)
                clients = settings.get('clients', [])
                
                for client_config in clients:
                    if client_config.get('enable'):
                        email = client_config.get('email')
                        if email:
                            active_emails.add(email)
                            print(f"✅ Активный в 3xUI: {email}")
                            
            except json.JSONDecodeError as e:
                print(f"Ошибка парсинга settings: {e}")
    
    print(f"\n📊 Найдено {len(active_emails)} активных клиентов в 3xUI")
    
    # Обновляем статус в базе данных
    db = SessionLocal()
    try:
        print("\n🔄 Обновление статуса в базе данных...")
        
        # Получаем всех пользователей
        users = db.query(User).all()
        
        for user in users:
            print(f"\n👤 Пользователь: {user.full_name} ({user.email})")
            
            # Получаем все подписки пользователя
            subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
            
            if user.email in active_emails:
                print(f"   ✅ Клиент активен в 3xUI")
                # Помечаем все подписки как активные
                for sub in subscriptions:
                    if sub.status != "active":
                        print(f"   🔄 Активируем подписку ID: {sub.id}")
                        sub.status = "active"
            else:
                print(f"   ❌ Клиент не найден в 3xUI")
                # Помечаем все подписки как истекшие
                for sub in subscriptions:
                    if sub.status == "active":
                        print(f"   🔄 Деактивируем подписку ID: {sub.id}")
                        sub.status = "expired"
            
            db.commit()
        
        print("\n✅ Синхронизация завершена!")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(sync_subscription_status())
