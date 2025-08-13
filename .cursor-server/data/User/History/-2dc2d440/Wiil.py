#!/usr/bin/env python3
"""
Скрипт для изменения типа telegram_id на BIGINT
"""

import psycopg2
from config import DATABASE_URL
import re

def migrate_telegram_id_bigint():
    """Изменяет тип telegram_id на BIGINT"""
    
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
        
        print("🔍 Проверяем текущий тип telegram_id...")
        
        # Проверяем текущий тип
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'telegram_id'
        """)
        
        result = cursor.fetchone()
        if result:
            column_name, data_type = result
            print(f"   Текущий тип: {data_type}")
            
            if data_type == 'bigint':
                print("✅ Тип уже BIGINT, миграция не нужна")
                return
            elif data_type == 'integer':
                print("🔧 Изменяем тип с INTEGER на BIGINT...")
            else:
                print(f"⚠️  Неожиданный тип: {data_type}")
                return
        else:
            print("❌ Колонка telegram_id не найдена")
            return
        
        # Изменяем тип на BIGINT
        cursor.execute("""
            ALTER TABLE users 
            ALTER COLUMN telegram_id TYPE BIGINT
        """)
        
        conn.commit()
        print("✅ Тип telegram_id успешно изменен на BIGINT!")
        
        # Проверяем результат
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'telegram_id'
        """)
        
        result = cursor.fetchone()
        if result:
            column_name, data_type = result
            print(f"   Новый тип: {data_type}")
        
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
    print("🚀 Запуск миграции для изменения типа telegram_id...")
    migrate_telegram_id_bigint()
    print("✅ Миграция завершена!")
