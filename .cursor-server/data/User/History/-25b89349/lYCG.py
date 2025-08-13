#!/usr/bin/env python3
"""
Скрипт для принудительной синхронизации всех подписок с 3xUI
"""

import asyncio
from database import SessionLocal, User, Subscription
from xui_client import XUIClient
from datetime import datetime

async def sync_all_subscriptions():
    """Принудительная синхронизация всех подписок"""
    print("🔄 Начинаем принудительную синхронизацию подписок...")
    
    db = SessionLocal()
    try:
        # Получаем все подписки
        all_subscriptions = db.query(Subscription).all()
        print(f"📊 Всего подписок в БД: {len(all_subscriptions)}")
        
        # Синхронизируем с 3xUI
        xui_client = XUIClient()
        sync_result = await xui_client.sync_subscriptions()
        
        if sync_result.get("success"):
            active_clients = sync_result.get("active_clients", [])
            active_emails = [client["email"] for client in active_clients]
            
            print(f"📊 Активных клиентов в 3xUI: {len(active_clients)}")
            print(f"📧 Активные email в 3xUI: {active_emails}")
            
            updated_count = 0
            
            for subscription in all_subscriptions:
                user = db.query(User).filter(User.id == subscription.user_id).first()
                if user:
                    user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
                    
                    # Проверяем статус подписки
                    if subscription.status == "active":
                        if user_email not in active_emails:
                            # Подписка помечена как активная, но пользователя нет в 3xUI
                            subscription.status = "expired"
                            print(f"❌ Подписка пользователя {user.telegram_id} ({user_email}) помечена как истекшая (удалена из 3xUI)")
                            updated_count += 1
                        elif subscription.expires_at <= datetime.utcnow():
                            # Подписка истекла по времени
                            subscription.status = "expired"
                            print(f"⏰ Подписка пользователя {user.telegram_id} ({user_email}) помечена как истекшая (по времени)")
                            updated_count += 1
                        else:
                            print(f"✅ Подписка пользователя {user.telegram_id} ({user_email}) активна")
                    else:
                        print(f"📋 Подписка пользователя {user.telegram_id} ({user_email}) уже помечена как {subscription.status}")
            
            db.commit()
            print(f"✅ Синхронизация завершена! Обновлено подписок: {updated_count}")
            
        else:
            print(f"❌ Ошибка синхронизации с 3xUI: {sync_result.get('msg', 'Неизвестная ошибка')}")
            
    except Exception as e:
        print(f"❌ Ошибка при синхронизации: {e}")
        db.rollback()
    finally:
        db.close()
        await xui_client.close()

if __name__ == "__main__":
    asyncio.run(sync_all_subscriptions())
