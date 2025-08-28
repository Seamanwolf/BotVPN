#!/usr/bin/env python3
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Настройки базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://vpn_user:vpn_password@localhost/vpn_bot")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def migrate_first_login():
    """Добавляет поле first_login в таблицу admins"""
    db = SessionLocal()
    try:
        # Проверяем, существует ли уже поле first_login
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'admins' AND column_name = 'first_login'
        """))
        
        if result.fetchone():
            print("Поле first_login уже существует в таблице admins")
            return
        
        # Добавляем поле first_login
        db.execute(text("""
            ALTER TABLE admins 
            ADD COLUMN first_login BOOLEAN DEFAULT TRUE
        """))
        
        # Обновляем существующие записи - если уже был вход, то first_login = FALSE
        db.execute(text("""
            UPDATE admins 
            SET first_login = FALSE 
            WHERE last_login IS NOT NULL
        """))
        
        db.commit()
        print("✅ Поле first_login успешно добавлено в таблицу admins")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при миграции: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_first_login()
