#!/usr/bin/env python3
"""
Скрипт для добавления поля has_made_first_purchase
"""

import psycopg2
from config import DATABASE_URL
import re

def migrate_first_purchase():
    """Добавляет поле has_made_first_purchase"""
    
    # Извлекаем параметры подключения из DATABASE_URL
    match = re.match(r'postgresql://([^:]+):([^@]+)@([^/]+)/(.+)', DATABASE_URL)
    if not match:
        print("❌ Неверный формат DATABASE_URL")
        return
    
    user, password, host, dbname = match.groups()
    
    try:
        # Подключаемся к базе данных
        conn = psycopg2.connect(
            host=host,
            database=dbname,
            user=user,
            password=password
        )
        cursor = conn.cursor()
        
        print("🔍 Проверяем существование поля has_made_first_purchase...")
        
        # Проверяем, существует ли поле
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'has_made_first_purchase'
        """)
        
        if cursor.fetchone():
            print("✅ Поле has_made_first_purchase уже существует")
            return
        
        print("🔧 Добавляем поле has_made_first_purchase...")
        
        # Добавляем поле
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN has_made_first_purchase BOOLEAN DEFAULT FALSE
        """)
        
        conn.commit()
        print("✅ Поле has_made_first_purchase успешно добавлено!")
        
    except psycopg2.Error as e:
        print(f"❌ Ошибка базы данных: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    print("🚀 Запуск миграции для добавления поля has_made_first_purchase...")
    migrate_first_purchase()
    print("✅ Миграция завершена!")
