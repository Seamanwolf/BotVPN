#!/usr/bin/env python3
"""
Миграция для добавления поля ticket_type в таблицу tickets
"""

import sys
import os
from datetime import datetime

# Добавляем родительскую директорию в путь для импорта
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import create_engine, Column, String, text
from sqlalchemy.ext.declarative import declarative_base
from database import SessionLocal, Ticket

def run_migration():
    """Добавляет поле ticket_type в таблицу tickets"""
    engine = create_engine(os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/seavpn"))
    connection = engine.connect()
    
    try:
        print("Начинаем миграцию...")
        
        # Проверяем, существует ли уже колонка ticket_type
        try:
            connection.execute(text("SELECT ticket_type FROM tickets LIMIT 1"))
            print("Колонка ticket_type уже существует. Миграция не требуется.")
            return
        except Exception:
            print("Колонка ticket_type не найдена. Добавляем...")
            connection.close()
            connection = engine.connect()
        
        # Добавляем колонку ticket_type
        connection.execute(text("ALTER TABLE tickets ADD COLUMN ticket_type VARCHAR DEFAULT 'support'"))
        connection.commit()
        
        print("Миграция успешно завершена!")
    except Exception as e:
        if connection.in_transaction():
            connection.rollback()
        print(f"Ошибка при выполнении миграции: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    run_migration()
