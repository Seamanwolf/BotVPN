#!/usr/bin/env python3
"""
Скрипт для проверки и исправления статусов подписок
"""

import os
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

def fix_subscription_statuses():
    """Проверяет и исправляет статусы подписок"""
    
    # Создаем подключение к базе данных
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    print("🔍 Проверяем статусы подписок...")
    
    with engine.connect() as conn:
        # Получаем все подписки
        result = conn.execute(text("""
            SELECT id, user_id, plan, status, expires_at, key_number 
            FROM subscriptions 
            ORDER BY user_id, key_number
        """))
        
        subscriptions = result.fetchall()
        
        print(f"📊 Найдено {len(subscriptions)} подписок")
        
        for sub in subscriptions:
            sub_id, user_id, plan, status, expires_at, key_number = sub
            
            # Проверяем, истекла ли подписка
            if expires_at:
                now = datetime.now(timezone.utc)
                days_left = (expires_at - now).days
                
                # Определяем правильный статус
                if days_left <= 0:
                    correct_status = "expired"
                else:
                    correct_status = "active"
                
                print(f"Ключ #{key_number} (ID: {sub_id}):")
                print(f"  План: {plan}")
                print(f"  Текущий статус: {status}")
                print(f"  Правильный статус: {correct_status}")
                print(f"  Истекает: {expires_at}")
                print(f"  Осталось дней: {days_left}")
                
                # Исправляем статус если нужно
                if status != correct_status:
                    print(f"  🔧 Исправляем статус с '{status}' на '{correct_status}'")
                    conn.execute(text("""
                        UPDATE subscriptions 
                        SET status = :status 
                        WHERE id = :sub_id
                    """), {"status": correct_status, "sub_id": sub_id})
                else:
                    print(f"  ✅ Статус корректен")
                
                print()
        
        conn.commit()
        print("🎉 Проверка и исправление завершены!")

if __name__ == "__main__":
    print("🚀 Запуск проверки статусов подписок...")
    fix_subscription_statuses()
