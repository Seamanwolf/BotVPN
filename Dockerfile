FROM python:3.10-slim

WORKDIR /app

# Установка необходимых пакетов
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements.txt и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всех файлов проекта
COPY . .

# Создание директории для логов
RUN mkdir -p /var/log/seavpn

# Экспорт переменных окружения
ENV PYTHONUNBUFFERED=1

# Запуск бота и webhook сервера
CMD ["sh", "-c", "python bot.py & python webhook_handler.py"]


