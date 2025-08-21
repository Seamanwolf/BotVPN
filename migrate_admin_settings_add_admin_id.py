#!/usr/bin/env python3
from sqlalchemy import text
from database import SessionLocal

def migrate():
    db = SessionLocal()
    try:
        # Добавляем столбец admin_id, если его нет
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='admin_settings' AND column_name='admin_id'
                ) THEN
                    ALTER TABLE admin_settings
                    ADD COLUMN admin_id INTEGER REFERENCES admins(id);
                END IF;
            END$$;
        """))
        db.commit()
        print("✅ admin_settings.admin_id добавлен (или уже существовал)")
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
