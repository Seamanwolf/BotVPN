#!/usr/bin/env python3
"""
Скрипт для миграции базы данных
Добавляет новые поля для реферальной системы
"""

from database import engine, Base, SessionLocal, User
from sqlalchemy import text

def migrate_database():
    """Миграция базы данных"""
    print("Начинаем миграцию базы данных...")
    
    # Создаем новые таблицы
    Base.metadata.create_all(bind=engine)
    
    # Добавляем новые колонки если их нет
    with engine.connect() as conn:
        try:
            # Проверяем существование колонки referral_code
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='referral_code'
            """))
            
            if not result.fetchone():
                print("Добавляем колонку referral_code...")
                conn.execute(text("ALTER TABLE users ADD COLUMN referral_code VARCHAR"))
                conn.execute(text("CREATE UNIQUE INDEX ix_users_referral_code ON users(referral_code)"))
            
            # Проверяем существование колонки referred_by
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='referred_by'
            """))
            
            if not result.fetchone():
                print("Добавляем колонку referred_by...")
                conn.execute(text("ALTER TABLE users ADD COLUMN referred_by INTEGER"))
                conn.execute(text("ALTER TABLE users ADD CONSTRAINT fk_users_referred_by FOREIGN KEY (referred_by) REFERENCES users(id)"))
            
            # Проверяем существование колонки bonus_coins
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='bonus_coins'
            """))
            
            if not result.fetchone():
                print("Добавляем колонку bonus_coins...")
                conn.execute(text("ALTER TABLE users ADD COLUMN bonus_coins INTEGER DEFAULT 0"))
            
            conn.commit()
            print("Миграция завершена успешно!")
            
        except Exception as e:
            print(f"Ошибка при миграции: {e}")
            conn.rollback()

if __name__ == "__main__":
    migrate_database()
