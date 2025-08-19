#!/usr/bin/env python3
"""
Скрипт для создания таблиц тикетов в базе данных
"""

import sys
import os
import logging

# Добавляем родительскую директорию в путь для импорта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import Base, engine, Ticket, TicketMessage

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_tables():
    """Создание таблиц в базе данных"""
    try:
        # Создаем таблицы
        Base.metadata.create_all(engine, tables=[
            Ticket.__table__,
            TicketMessage.__table__
        ])
        logger.info("Таблицы успешно созданы")
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}")
        raise

if __name__ == "__main__":
    create_tables()
    print("Таблицы для тикетов успешно созданы")

