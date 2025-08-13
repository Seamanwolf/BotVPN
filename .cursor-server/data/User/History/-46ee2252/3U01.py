#!/usr/bin/env python3
"""
Скрипт для создания суперадмина
"""

from database import SessionLocal, Admin
from werkzeug.security import generate_password_hash
from datetime import datetime

def create_superadmin():
    """Создание суперадмина"""
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже суперадмин
        existing_admin = db.query(Admin).filter(Admin.telegram_id == 261337953).first()
        
        if existing_admin:
            print("Суперадмин уже существует!")
            return
        
        # Создаем суперадмина
        superadmin = Admin(
            telegram_id=261337953,
            username="Admin",
            full_name="Главный администратор",
            password_hash=generate_password_hash("CegthGfzkmybr72"),
            is_superadmin=True,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(superadmin)
        db.commit()
        
        print("✅ Суперадмин успешно создан!")
        print(f"Telegram ID: 261337953")
        print(f"Логин: Admin")
        print(f"Пароль: CegthGfzkmybr72")
        
    except Exception as e:
        print(f"❌ Ошибка создания суперадмина: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_superadmin()

