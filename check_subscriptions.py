#!/usr/bin/env python3
"""
Скрипт для проверки статуса подписок в базе данных
"""

from database import SessionLocal, User, Subscription
from datetime import datetime, timedelta

def check_subscriptions():
    """Проверка всех подписок в базе данных"""
    print("🔍 Проверяем подписки в базе данных...")
    
    db = SessionLocal()
    try:
        # Получаем все подписки
        all_subscriptions = db.query(Subscription).all()
        print(f"📊 Всего подписок в БД: {len(all_subscriptions)}")
        
        for subscription in all_subscriptions:
            user = db.query(User).filter(User.id == subscription.user_id).first()
            if user:
                user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
                days_left = (subscription.expires_at - datetime.utcnow()).days
                
                print(f"\n📋 Подписка ID: {subscription.id}")
                print(f"   Пользователь: {user.telegram_id} ({user_email})")
                print(f"   Тариф: {subscription.plan}")
                print(f"   Статус: {subscription.status}")
                print(f"   Дата истечения: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}")
                print(f"   Дней осталось: {days_left}")
                print(f"   Создана: {subscription.created_at.strftime('%d.%m.%Y %H:%M')}")
        
        # Проверяем активные подписки
        active_subscriptions = db.query(Subscription).filter(Subscription.status == "active").all()
        print(f"\n✅ Активных подписок: {len(active_subscriptions)}")
        
        # Проверяем истекшие подписки
        expired_subscriptions = db.query(Subscription).filter(Subscription.status == "expired").all()
        print(f"❌ Истекших подписок: {len(expired_subscriptions)}")
        
        # Проверяем подписки, которые истекают сегодня
        today = datetime.utcnow().date()
        expiring_today = db.query(Subscription).filter(
            Subscription.status == "active",
            Subscription.expires_at >= datetime.utcnow(),
            Subscription.expires_at < datetime.utcnow() + timedelta(days=1)
        ).all()
        
        print(f"⚠️ Подписок, истекающих сегодня: {len(expiring_today)}")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_subscriptions()

