#!/usr/bin/env python3
"""
Миграция для добавления таблицы админов
"""

from database import engine, SessionLocal, Admin
from werkzeug.security import generate_password_hash
from config import ADMIN_IDS

def migrate_admins():
    """Добавление таблицы админов и создание суперадмина"""
    print("🔧 Создаем таблицу админов...")
    
    # Создаем таблицу админов
    from database import Base
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже админы
        existing_admins = db.query(Admin).count()
        if existing_admins > 0:
            print("✅ Таблица админов уже существует")
            return
        
        # Создаем суперадмина
        superadmin = Admin(
            telegram_id=261337953,  # Главный админ
            username="superadmin",
            full_name="Главный администратор",
            password_hash=generate_password_hash("admin123"),  # Временный пароль
            is_superadmin=True,
            is_active=True
        )
        
        db.add(superadmin)
        db.commit()
        
        print("✅ Суперадмин создан:")
        print(f"   Telegram ID: {superadmin.telegram_id}")
        print(f"   Логин: {superadmin.username}")
        print(f"   Пароль: admin123")
        print("⚠️ Не забудьте изменить пароль!")
        
    except Exception as e:
        print(f"❌ Ошибка при создании админов: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_admins()
