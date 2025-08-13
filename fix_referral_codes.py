#!/usr/bin/env python3
"""
Скрипт для исправления реферальных кодов существующих пользователей
"""

from database import SessionLocal, User, generate_referral_code

def fix_referral_codes():
    """Исправляем реферальные коды для существующих пользователей"""
    db = SessionLocal()
    try:
        # Получаем всех пользователей без реферального кода
        users_without_code = db.query(User).filter(User.referral_code.is_(None)).all()
        
        print(f"Найдено {len(users_without_code)} пользователей без реферального кода")
        
        for user in users_without_code:
            # Генерируем уникальный код
            new_code = generate_referral_code()
            
            # Проверяем, что код уникальный
            while db.query(User).filter(User.referral_code == new_code).first():
                new_code = generate_referral_code()
            
            # Обновляем пользователя
            user.referral_code = new_code
            print(f"Пользователь {user.full_name} (ID: {user.id}) получил код: {new_code}")
        
        db.commit()
        print("Реферальные коды успешно обновлены!")
        
        # Показываем статистику
        total_users = db.query(User).count()
        users_with_code = db.query(User).filter(User.referral_code.isnot(None)).count()
        print(f"Всего пользователей: {total_users}")
        print(f"С реферальными кодами: {users_with_code}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_referral_codes()
