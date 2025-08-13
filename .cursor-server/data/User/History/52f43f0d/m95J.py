#!/usr/bin/env python3
"""
Скрипт для проверки админов в базе данных
"""

from database import SessionLocal, Admin

def check_admins():
    """Проверка админов в базе данных"""
    print("🔍 Проверяем админов в базе данных...")
    
    db = SessionLocal()
    try:
        admins = db.query(Admin).all()
        print(f"📊 Всего админов в БД: {len(admins)}")
        
        for admin in admins:
            print(f"\n📋 Админ ID: {admin.id}")
            print(f"   Telegram ID: {admin.telegram_id}")
            print(f"   Логин: {admin.username}")
            print(f"   Полное имя: {admin.full_name}")
            print(f"   Суперадмин: {admin.is_superadmin}")
            print(f"   Активен: {admin.is_active}")
            print(f"   Создан: {admin.created_at.strftime('%d.%m.%Y %H:%M')}")
            print(f"   Последний вход: {admin.last_login.strftime('%d.%m.%Y %H:%M') if admin.last_login else 'Никогда'}")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_admins()

