#!/usr/bin/env python3
"""
Скрипт для исправления статуса подписок на основе реальных данных из 3xUI
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from database import SessionLocal, User, Subscription
from xui_client import XUIClient

async def fix_subscriptions():
    """Исправление статуса подписок на основе данных из 3xUI"""
    
    # Получаем список активных клиентов из 3xUI
    print("🔍 Получение списка активных клиентов из 3xUI...")
    xui_client = XUIClient()
    await xui_client.login()
    inbounds = await xui_client.get_inbounds()
    
    active_clients = {}
    if inbounds and inbounds.get('obj'):
        for inbound in inbounds['obj']:
            settings_str = inbound.get('settings', '{}')
            try:
                settings = json.loads(settings_str)
                clients = settings.get('clients', [])
                
                for client_config in clients:
                    if client_config.get('enable'):
                        email = client_config.get('email')
                        client_id = client_config.get('id')
                        expiry_time = client_config.get('expiryTime', 0)
                        tg_id = client_config.get('tgId')
                        
                        if email:
                            active_clients[email] = {
                                'id': client_id,
                                'expiry_time': expiry_time,
                                'tg_id': tg_id,
                                'sub_id': client_config.get('subId')
                            }
                            print(f"✅ Активный клиент: {email} (ID: {client_id})")
                            
            except json.JSONDecodeError as e:
                print(f"Ошибка парсинга settings: {e}")
    
    print(f"\n📊 Найдено {len(active_clients)} активных клиентов в 3xUI")
    
    # Исправляем записи в базе данных
    db = SessionLocal()
    try:
        print("\n🔧 Исправление записей в базе данных...")
        
        # Получаем всех пользователей
        users = db.query(User).all()
        
        for user in users:
            print(f"\n👤 Пользователь: {user.full_name} ({user.email})")
            
            if user.email in active_clients:
                client_info = active_clients[user.email]
                print(f"   ✅ Клиент активен в 3xUI")
                print(f"   ID: {client_info['id']}")
                print(f"   TG ID: {client_info['tg_id']}")
                
                # Конвертируем время истечения из миллисекунд
                if client_info['expiry_time'] > 0:
                    epoch = datetime.fromtimestamp(0, timezone.utc)
                    expiry_date = epoch + timedelta(milliseconds=client_info['expiry_time'])
                    print(f"   Истекает: {expiry_date}")
                else:
                    expiry_date = None
                    print(f"   Бессрочная подписка")
                
                # Получаем все подписки пользователя
                subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
                
                if len(subscriptions) > 1:
                    print(f"   ⚠️ Найдено {len(subscriptions)} подписок, оставляем самую новую")
                    
                    # Сортируем по дате создания
                    sorted_subs = sorted(subscriptions, key=lambda x: x.created_at, reverse=True)
                    
                    # Удаляем все кроме самой новой
                    for sub in sorted_subs[1:]:
                        print(f"   🗑️ Удаляем подписку ID: {sub.id}")
                        db.delete(sub)
                    
                    # Обновляем оставшуюся подписку
                    main_subscription = sorted_subs[0]
                    main_subscription.status = "active"
                    if expiry_date:
                        main_subscription.expires_at = expiry_date
                    
                    print(f"   ✅ Обновлена подписка ID: {main_subscription.id}")
                else:
                    # Обновляем единственную подписку
                    for sub in subscriptions:
                        sub.status = "active"
                        if expiry_date:
                            sub.expires_at = expiry_date
                        print(f"   ✅ Обновлена подписка ID: {sub.id}")
                
                db.commit()
                
            else:
                print(f"   ❌ Клиент не найден в 3xUI")
                
                # Помечаем все подписки как истекшие
                subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
                for sub in subscriptions:
                    if sub.status == "active":
                        print(f"   🔄 Помечаем подписку ID: {sub.id} как истекшую")
                        sub.status = "expired"
                
                db.commit()
        
        print("\n✅ Исправление базы данных завершено!")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(fix_subscriptions())
