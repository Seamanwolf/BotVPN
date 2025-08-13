#!/usr/bin/env python3
"""
Скрипт для добавления номеров ключей к существующим подпискам
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

def add_key_numbers():
    """Добавляет номера ключей к существующим подпискам"""
    
    # Создаем подключение к базе данных
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    print("🔍 Проверяем существование поля key_number...")
    
    # Проверяем, существует ли поле key_number
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'subscriptions' AND column_name = 'key_number'
        """))
        
        if result.fetchone():
            print("✅ Поле key_number уже существует")
        else:
            print("🔧 Добавляем поле key_number...")
            conn.execute(text("ALTER TABLE subscriptions ADD COLUMN key_number INTEGER"))
            conn.commit()
            print("✅ Поле key_number успешно добавлено!")
    
    print("🔧 Назначаем номера ключей для существующих подписок...")
    
    # Получаем всех пользователей с подписками
    with engine.connect() as conn:
        # Получаем пользователей с подписками, отсортированных по времени создания
        result = conn.execute(text("""
            SELECT DISTINCT user_id 
            FROM subscriptions 
            ORDER BY user_id
        """))
        
        user_ids = [row[0] for row in result.fetchall()]
        
        for user_id in user_ids:
            print(f"👤 Обрабатываем пользователя {user_id}...")
            
            # Получаем подписки пользователя, отсортированные по времени создания
            result = conn.execute(text("""
                SELECT id, created_at 
                FROM subscriptions 
                WHERE user_id = :user_id 
                ORDER BY created_at ASC
            """), {"user_id": user_id})
            
            subscriptions = result.fetchall()
            
            # Назначаем номера ключей
            for i, (sub_id, created_at) in enumerate(subscriptions, 1):
                conn.execute(text("""
                    UPDATE subscriptions 
                    SET key_number = :key_number 
                    WHERE id = :sub_id
                """), {"key_number": i, "sub_id": sub_id})
                
                print(f"  📝 Подписка {sub_id} -> Ключ #{i}")
            
            conn.commit()
            print(f"✅ Пользователь {user_id}: назначено {len(subscriptions)} ключей")
    
    print("🎉 Миграция завершена успешно!")
    print("📊 Статистика:")
    
    # Показываем статистику
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total_subscriptions,
                COUNT(DISTINCT user_id) as total_users,
                AVG(key_number) as avg_keys_per_user
            FROM subscriptions
        """))
        
        stats = result.fetchone()
        print(f"• Всего подписок: {stats[0]}")
        print(f"• Всего пользователей: {stats[1]}")
        print(f"• Среднее количество ключей на пользователя: {stats[2]:.1f}")

if __name__ == "__main__":
    print("🚀 Запуск миграции для добавления номеров ключей...")
    add_key_numbers()
