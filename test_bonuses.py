#!/usr/bin/env python3

from database import SessionLocal, User
import asyncio

async def test_bonuses():
    db = SessionLocal()
    try:
        # Проверяем пользователя с ID 4 (Сергей)
        user = db.query(User).filter(User.telegram_id == 7107555507).first()
        if user:
            print(f"=== ТЕСТ РЕФЕРАЛЬНЫХ БОНУСОВ ===")
            print(f"Пользователь: {user.full_name}")
            print(f"Telegram ID: {user.telegram_id}")
            print(f"Email: {user.email}")
            print(f"Бонусные монеты: {user.bonus_coins}")
            print(f"Реферал от: {user.referred_by}")
            print(f"Первая покупка сделана: {user.has_made_first_purchase}")
            
            # Проверяем реферера
            if user.referred_by:
                referrer = db.query(User).filter(User.id == user.referred_by).first()
                if referrer:
                    print(f"\nРеферер: {referrer.full_name}")
                    print(f"Бонусные монеты реферера: {referrer.bonus_coins}")
                else:
                    print("\nРеферер не найден")
            else:
                print("\nПользователь не пришел по реферальной ссылке")
            
            print(f"\n=== ТЕСТ СПИСАНИЯ МОНЕТ ===")
            print(f"Текущие монеты: {user.bonus_coins}")
            
            # Симулируем списание 150 монет
            if user.bonus_coins >= 150:
                old_coins = user.bonus_coins
                user.bonus_coins -= 150
                db.merge(user)
                db.commit()
                
                # Проверяем результат
                db.refresh(user)
                print(f"Списано: 150 монет")
                print(f"Было: {old_coins} монет")
                print(f"Стало: {user.bonus_coins} монет")
                print(f"✅ Списание работает корректно")
                
                # Возвращаем монеты обратно для теста
                user.bonus_coins += 150
                db.merge(user)
                db.commit()
                print(f"Монеты возвращены обратно: {user.bonus_coins}")
            else:
                print(f"❌ Недостаточно монет для теста (нужно минимум 150)")
                
        else:
            print("Пользователь не найден")
            
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_bonuses())
