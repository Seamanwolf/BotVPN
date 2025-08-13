#!/usr/bin/env python3
"""
Скрипт для очистки дублирующихся подписок
"""

from database import SessionLocal, User, Subscription
from datetime import datetime
import asyncio
from xui_client import XUIClient

async def cleanup_subscriptions():
    """Очистка дублирующихся подписок"""
    print("🧹 Очищаем дублирующиеся подписки...")
    
    # Сначала синхронизируем с 3xUI
    xui_client = XUIClient()
    try:
        sync_result = await xui_client.sync_subscriptions()
        if sync_result.get("success"):
            active_clients = sync_result.get("active_clients", [])
            active_emails = [client["email"] for client in active_clients]
            print(f"📊 Активных клиентов в 3xUI: {len(active_clients)}")
        else:
            print(f"❌ Ошибка синхронизации с 3xUI: {sync_result.get('msg', 'Неизвестная ошибка')}")
            return
    finally:
        await xui_client.close()
    
    db = SessionLocal()
    try:
        # Получаем всех пользователей
        users = db.query(User).all()
        
        for user in users:
            user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
            
            # Получаем все подписки пользователя
            subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
            
            if len(subscriptions) > 1:
                print(f"\n👤 Пользователь {user.telegram_id} ({user.full_name}):")
                print(f"   Email: {user_email}")
                print(f"   Подписок в БД: {len(subscriptions)}")
                
                # Проверяем, есть ли пользователь в 3xUI
                if user_email in active_emails:
                    print(f"   ✅ Пользователь активен в 3xUI")
                    
                    # Оставляем только самую новую активную подписку
                    active_subscriptions = [s for s in subscriptions if s.status == "active"]
                    if active_subscriptions:
                        # Сортируем по дате создания, оставляем самую новую
                        active_subscriptions.sort(key=lambda x: x.created_at, reverse=True)
                        keep_subscription = active_subscriptions[0]
                        
                        print(f"   🔄 Оставляем подписку ID: {keep_subscription.id} (создана: {keep_subscription.created_at})")
                        
                        # Удаляем остальные активные подписки
                        for sub in active_subscriptions[1:]:
                            print(f"   🗑️ Удаляем дублирующуюся подписку ID: {sub.id}")
                            db.delete(sub)
                        
                        # Помечаем неактивные подписки как истекшие
                        for sub in subscriptions:
                            if sub.status == "active" and sub.id != keep_subscription.id:
                                sub.status = "expired"
                                print(f"   ⏰ Помечаем как истекшую подписку ID: {sub.id}")
                    else:
                        print(f"   ⚠️ Нет активных подписок")
                else:
                    print(f"   ❌ Пользователь не найден в 3xUI")
                    # Помечаем все подписки как истекшие
                    for sub in subscriptions:
                        if sub.status == "active":
                            sub.status = "expired"
                            print(f"   ⏰ Помечаем как истекшую подписку ID: {sub.id}")
        
        db.commit()
        print(f"\n✅ Очистка завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка при очистке: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(cleanup_subscriptions())

