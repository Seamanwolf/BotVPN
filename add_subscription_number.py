#!/usr/bin/env python3
"""
Скрипт для добавления поля subscription_number в существующие подписки
"""

import asyncio
from sqlalchemy import create_engine, text
from database import DATABASE_URL

async def add_subscription_number_field():
    """Добавляет поле subscription_number в таблицу subscriptions"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Проверяем, существует ли уже поле subscription_number
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'subscriptions' 
            AND column_name = 'subscription_number'
        """))
        
        if result.fetchone():
            print("Поле subscription_number уже существует")
            return
        
        # Добавляем поле subscription_number
        conn.execute(text("""
            ALTER TABLE subscriptions 
            ADD COLUMN subscription_number INTEGER DEFAULT 1
        """))
        
        # Обновляем существующие подписки, присваивая уникальные номера
        conn.execute(text("""
            UPDATE subscriptions 
            SET subscription_number = (
                SELECT COALESCE(MAX(s2.subscription_number), 0) + 1
                FROM subscriptions s2 
                WHERE s2.user_id = subscriptions.user_id 
                AND s2.id < subscriptions.id
            )
            WHERE subscription_number = 1
        """))
        
        conn.commit()
        print("Поле subscription_number успешно добавлено и заполнено")

if __name__ == "__main__":
    asyncio.run(add_subscription_number_field())
