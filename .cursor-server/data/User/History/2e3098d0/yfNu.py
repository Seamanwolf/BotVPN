#!/usr/bin/env python3
"""
Скрипт для обновления данных суперадмина
"""

from database import SessionLocal, Admin
from werkzeug.security import generate_password_hash
from datetime import datetime

def update_superadmin():
    db = SessionLocal()
    try:
        # Ищем существующего суперадмина
        admin = db.query(Admin).filter(Admin.telegram_id == 261337953).first()
        
        if admin:
            print(f"Найден существующий админ: {admin.username}")
            print(f"Текущий статус: {'Активен' if admin.is_active else 'Неактивен'}")
            print(f"Роль: {'Суперадмин' if admin.is_superadmin else 'Администратор'}")
            
            # Обновляем данные
            admin.username = "Admin"
            admin.full_name = "Главный администратор"
            admin.password_hash = generate_password_hash("CegthGfzkmybr72")
            admin.is_superadmin = True
            admin.is_active = True
            admin.last_login = None
            
            db.commit()
            print("✅ Данные суперадмина обновлены!")
            print(f"Логин: {admin.username}")
            print(f"Пароль: CegthGfzkmybr72")
            print(f"Telegram ID: {admin.telegram_id}")
            
        else:
            print("❌ Суперадмин не найден! Создаем нового...")
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
            print("✅ Новый суперадмин создан!")
            print(f"Логин: {superadmin.username}")
            print(f"Пароль: CegthGfzkmybr72")
            print(f"Telegram ID: {superadmin.telegram_id}")
            
    except Exception as e:
        print(f"❌ Ошибка обновления суперадмина: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_superadmin()
