#!/usr/bin/env python3
"""
Миграция для добавления колонки plan_name в таблицу subscriptions
"""

from database import engine, SessionLocal
from sqlalchemy import text

def migrate_plan_name():
    """Добавление колонки plan_name"""
    print("🔧 Добавляем колонку plan_name...")
    
    db = SessionLocal()
    try:
        # Проверяем, существует ли колонка
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'subscriptions' AND column_name = 'plan_name'
        """))
        
        if result.fetchone():
            print("✅ Колонка plan_name уже существует")
            return
        
        # Добавляем колонку
        db.execute(text("ALTER TABLE subscriptions ADD COLUMN plan_name VARCHAR"))
        
        # Обновляем существующие записи
        db.execute(text("""
            UPDATE subscriptions 
            SET plan_name = CASE 
                WHEN plan = 'test' THEN 'Test'
                WHEN plan = '1m' THEN '1 месяц'
                WHEN plan = '3m' THEN '3 месяца'
                ELSE plan
            END
        """))
        
        db.commit()
        print("✅ Колонка plan_name добавлена и заполнена")
        
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_plan_name()
