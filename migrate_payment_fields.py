#!/usr/bin/env python3
"""
Миграция для добавления полей payment_type и payment_metadata в таблицу payments
"""

import json
from sqlalchemy import text
from database import engine, SessionLocal

def migrate_payment_fields():
    """Добавление полей payment_type и payment_metadata в таблицу payments"""
    try:
        print("Начинаем миграцию таблицы payments...")
        
        # Создаем подключение к базе данных
        with engine.connect() as connection:
            # Проверяем, существуют ли уже поля
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'payments' 
                AND column_name IN ('payment_type', 'payment_metadata')
            """))
            
            existing_columns = [row[0] for row in result]
            print(f"Существующие поля: {existing_columns}")
            
            # Добавляем поле payment_type если его нет
            if 'payment_type' not in existing_columns:
                print("Добавляем поле payment_type...")
                connection.execute(text("""
                    ALTER TABLE payments 
                    ADD COLUMN payment_type VARCHAR
                """))
                print("✅ Поле payment_type добавлено")
            else:
                print("Поле payment_type уже существует")
            
            # Добавляем поле payment_metadata если его нет
            if 'payment_metadata' not in existing_columns:
                print("Добавляем поле payment_metadata...")
                connection.execute(text("""
                    ALTER TABLE payments 
                    ADD COLUMN payment_metadata TEXT
                """))
                print("✅ Поле payment_metadata добавлено")
            else:
                print("Поле payment_metadata уже существует")
            
            # Обновляем существующие записи
            print("Обновляем существующие записи...")
            connection.execute(text("""
                UPDATE payments 
                SET payment_type = 'new' 
                WHERE payment_type IS NULL
            """))
            print("✅ Существующие записи обновлены")
            
            connection.commit()
            print("🎉 Миграция завершена успешно!")
            
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")
        raise

if __name__ == "__main__":
    migrate_payment_fields()
