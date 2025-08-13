#!/usr/bin/env python3
"""
Тест для проверки отображения множественных ключей
"""

import asyncio
from database import SessionLocal, User, Subscription
from xui_client import XUIClient
from datetime import datetime, timedelta

async def test_multiple_keys():
    """Тестируем отображение множественных ключей"""
    
    # Инициализируем клиент 3xUI
    xui_client = XUIClient()
    
    try:
        # Получаем пользователя (замените на реальный Telegram ID)
        telegram_id = 7107555507  # Ваш Telegram ID
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                print(f"Пользователь с Telegram ID {telegram_id} не найден")
                return
            
            print(f"Найден пользователь: {user.full_name}")
            
            # Получаем все активные подписки
            active_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.status == "active",
                Subscription.expires_at > datetime.utcnow()
            ).order_by(Subscription.subscription_number).all()
            
            print(f"Найдено активных подписок: {len(active_subscriptions)}")
            
            if active_subscriptions:
                print("\n=== АКТИВНЫЕ ПОДПИСКИ ===")
                for subscription in active_subscriptions:
                    print(f"\nПодписка #{subscription.subscription_number}")
                    print(f"Тариф: {subscription.plan_name}")
                    print(f"Статус: {subscription.status}")
                    print(f"Действует до: {subscription.expires_at}")
                    
                    # Получаем конфигурацию из 3xUI
                    user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
                    try:
                        config = await xui_client.get_user_config(user_email, subscription.subscription_number)
                        if config:
                            print(f"Конфигурация: {config}")
                        else:
                            print("❌ Конфигурация не найдена")
                    except Exception as e:
                        print(f"❌ Ошибка получения конфигурации: {e}")
            else:
                print("У пользователя нет активных подписок")
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        await xui_client.close()

if __name__ == "__main__":
    asyncio.run(test_multiple_keys())
