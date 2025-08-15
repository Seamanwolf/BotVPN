#!/bin/bash

echo "Установка systemd сервисов для SeaVPN..."

# Копирование сервисных файлов
sudo cp systemd/seavpn-bot.service /etc/systemd/system/
sudo cp systemd/seavpn-webhook.service /etc/systemd/system/
sudo cp systemd/seavpn-admin.service /etc/systemd/system/

# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение сервисов для автозапуска
sudo systemctl enable seavpn-bot.service
sudo systemctl enable seavpn-webhook.service
sudo systemctl enable seavpn-admin.service

# Запуск сервисов
sudo systemctl start seavpn-bot.service
sudo systemctl start seavpn-webhook.service
sudo systemctl start seavpn-admin.service

echo "Проверка статуса сервисов..."
sudo systemctl status seavpn-bot.service
sudo systemctl status seavpn-webhook.service
sudo systemctl status seavpn-admin.service

echo "Установка завершена!"


