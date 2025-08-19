#!/usr/bin/env python3

from database import engine, AdminSettings
from sqlalchemy import text

def create_admin_settings_table():
    """Создает таблицу admin_settings если она не существует"""
    try:
        with engine.connect() as conn:
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS admin_settings (
                    id SERIAL PRIMARY KEY,
                    admin_id INTEGER REFERENCES admins(id),
                    notifications_enabled BOOLEAN DEFAULT TRUE,
                    sounds_enabled BOOLEAN DEFAULT TRUE,
                    new_ticket_notifications BOOLEAN DEFAULT TRUE,
                    new_user_notifications BOOLEAN DEFAULT TRUE,
                    new_subscription_notifications BOOLEAN DEFAULT TRUE,
                    new_message_notifications BOOLEAN DEFAULT TRUE,
                    ticket_sound_enabled BOOLEAN DEFAULT TRUE,
                    user_sound_enabled BOOLEAN DEFAULT TRUE,
                    subscription_sound_enabled BOOLEAN DEFAULT TRUE,
                    message_sound_enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            conn.commit()
            print("Таблица admin_settings создана успешно!")
    except Exception as e:
        print(f"Ошибка при создании таблицы: {e}")

if __name__ == "__main__":
    create_admin_settings_table()
