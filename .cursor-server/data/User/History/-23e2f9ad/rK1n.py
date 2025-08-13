#!/usr/bin/env python3
"""
Скрипт для очистки базы данных от неактуальных записей подписок
"""

import asyncio
from datetime import datetime
from database import SessionLocal, User, Subscription
from xui_client import XUIClient

async def cleanup_database():
    """Очистка базы данных от неактуальных записей"""
    
    # Получаем список активных клиентов из 3xUI
    print("🔍 Получение списка активных клиентов из 3xUI...")
    xui_client = XUIClient()
    await xui_client.login()
    inbounds = await xui_client.get_inbounds()
    
    active_emails = set()
    if inbounds and inbounds.get('obj'):
        for inbound in inbounds['obj']:
            if 'clientStats' in inbound:
                for client_stat in inbound['clientStats']:
                    if client_stat.get('enable'):
                        email = client_stat.get('email')
                        if email:
                            active_emails.add(email)
                            print(f"✅ Активный клиент: {email}")
    
    print(f"\n📊 Найдено {len(active_emails)} активных клиентов в 3xUI")
    
    # Проверяем записи в базе данных
    db = SessionLocal()
    try:
        print("\n🔍 Проверка записей в базе данных...")
        
        # Получаем всех пользователей
        users = db.query(User).all()
        
        for user in users:
            print(f"\n👤 Пользователь: {user.full_name} ({user.email})")
            
            # Получаем все подписки пользователя
            subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
            print(f"   Подписок в БД: {len(subscriptions)}")
            
            # Проверяем, есть ли активный клиент в 3xUI
            if user.email in active_emails:
                print(f"   ✅ Клиент активен в 3xUI")
                
                # Оставляем только одну самую новую подписку
                if len(subscriptions) > 1:
                    print(f"   ⚠️ Найдено {len(subscriptions)} подписок, оставляем самую новую")
                    
                    # Сортируем по дате создания
                    sorted_subs = sorted(subscriptions, key=lambda x: x.created_at, reverse=True)
                    
                    # Удаляем все кроме самой новой
                    for sub in sorted_subs[1:]:
                        print(f"   🗑️ Удаляем подписку ID: {sub.id} (создана: {sub.created_at})")
                        db.delete(sub)
                    
                    db.commit()
                    print(f"   ✅ Оставлена подписка ID: {sorted_subs[0].id}")
            else:
                print(f"   ❌ Клиент не найден в 3xUI")
                
                # Если клиента нет в 3xUI, помечаем все подписки как истекшие
                for sub in subscriptions:
                    if sub.status == "active":
                        print(f"   🔄 Помечаем подписку ID: {sub.id} как истекшую")
                        sub.status = "expired"
                
                db.commit()
        
        print("\n✅ Очистка базы данных завершена!")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(cleanup_database())
