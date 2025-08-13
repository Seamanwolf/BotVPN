#!/usr/bin/env python3
"""
Скрипт для добавления уникальности email в существующую базу данных
"""

import psycopg2
from config import DATABASE_URL
import re

def migrate_email_unique():
    """Добавляет уникальность для email"""
    
    # Извлекаем параметры подключения из DATABASE_URL
    # postgresql://user:password@localhost/dbname
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
        
        print("🔍 Проверяем существующие email...")
        
        # Проверяем дубликаты email
        cursor.execute("""
            SELECT email, COUNT(*) 
            FROM users 
            WHERE email IS NOT NULL 
            GROUP BY email 
            HAVING COUNT(*) > 1
        """)
        
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"❌ Найдено {len(duplicates)} дубликатов email:")
            for email, count in duplicates:
                print(f"   {email}: {count} раз")
            
            print("\n⚠️  Необходимо удалить дубликаты перед добавлением уникальности!")
            print("   Рекомендуется оставить только самые новые записи для каждого email.")
            return
        
        print("✅ Дубликатов email не найдено")
        
        # Добавляем уникальность
        print("🔧 Добавляем уникальность для email...")
        cursor.execute("""
            ALTER TABLE users 
            ADD CONSTRAINT users_email_unique UNIQUE (email)
        """)
        
        conn.commit()
        print("✅ Уникальность email успешно добавлена!")
        
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
    print("🚀 Запуск миграции для добавления уникальности email...")
    migrate_email_unique()
    print("✅ Миграция завершена!")
