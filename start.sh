#!/bin/bash

echo "Запуск SeaVPN бота в Docker..."
docker-compose up -d --build

echo "Проверка статуса контейнера..."
docker-compose ps

echo "Просмотр логов (нажмите Ctrl+C для выхода):"
docker-compose logs -f


