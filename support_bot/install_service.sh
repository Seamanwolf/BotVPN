#!/bin/bash

# Установка зависимостей
pip3 install -r requirements.txt

# Копирование сервиса в systemd
cp seavpn-support-bot.service /etc/systemd/system/

# Перезагрузка systemd
systemctl daemon-reload

# Включение и запуск сервиса
systemctl enable seavpn-support-bot
systemctl start seavpn-support-bot

echo "Сервис установлен и запущен. Проверить статус: systemctl status seavpn-support-bot"
