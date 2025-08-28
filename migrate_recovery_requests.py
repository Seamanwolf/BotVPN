#!/usr/bin/env python3
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Настройки базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://vpn_user:vpn_password@localhost/vpn_bot")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def migrate_recovery_requests():
    """Создает таблицу recovery_requests"""
    db = SessionLocal()
    try:
        # Проверяем, существует ли уже таблица recovery_requests
        result = db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'recovery_requests'
        """))
        
        if result.fetchone():
            print("Таблица recovery_requests уже существует")
            return
        
        # Создаем таблицу recovery_requests
        db.execute(text("""
            CREATE TABLE recovery_requests (
                id SERIAL PRIMARY KEY,
                username VARCHAR NOT NULL,
                request_type VARCHAR NOT NULL,
                reason TEXT NOT NULL,
                contact VARCHAR NOT NULL,
                status VARCHAR DEFAULT 'pending',
                admin_id INTEGER REFERENCES admins(id),
                admin_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        """))
        
        # Создаем индексы
        db.execute(text("CREATE INDEX idx_recovery_requests_username ON recovery_requests(username)"))
        db.execute(text("CREATE INDEX idx_recovery_requests_status ON recovery_requests(status)"))
        db.execute(text("CREATE INDEX idx_recovery_requests_created_at ON recovery_requests(created_at)"))
        
        db.commit()
        print("✅ Таблица recovery_requests успешно создана")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Ошибка при миграции: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_recovery_requests()
