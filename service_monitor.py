#!/usr/bin/env python3
"""
Мониторинг systemd сервисов SeaVPN
Отправляет уведомления при падении сервисов
"""

import subprocess
import smtplib
import requests
import json
import time
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Создаем директорию для логов
os.makedirs('/var/log/seavpn', exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/seavpn/service_monitor.log'),
        logging.StreamHandler()
    ]
)

# Конфигурация
SERVICES = [
    'seavpn-bot.service',
    'seavpn-support-bot.service', 
    'seavpn-webhook.service',
    'seavpn-admin.service'
]

# Настройки уведомлений
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'your-email@example.com')
BOT_TOKEN = "8394863099:AAGQ3w7Y7WnYr9kfji_UcFc3jV-I--TIIvQ"
ADMIN_TELEGRAM_ID = 261337953  # Ваш Telegram ID

# Включить/отключить email уведомления
ENABLE_EMAIL_NOTIFICATIONS = False  # Отключаем email, оставляем только Telegram

# Состояние сервисов (для отслеживания изменений)
service_states = {}

def check_service_status(service_name):
    """Проверяет статус systemd сервиса"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() == 'active'
    except Exception as e:
        logging.error(f"Ошибка проверки сервиса {service_name}: {e}")
        return False

def get_service_logs(service_name, lines=10):
    """Получает последние логи сервиса"""
    try:
        result = subprocess.run(
            ['journalctl', '-u', service_name, '-n', str(lines), '--no-pager'],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout
    except Exception as e:
        logging.error(f"Ошибка получения логов {service_name}: {e}")
        return "Не удалось получить логи"

def send_email_notification(service_name, status, logs):
    """Отправляет уведомление на почту"""
    try:
        msg = MIMEMultipart()
        msg['From'] = 'root@seavpn.local'
        msg['To'] = ADMIN_EMAIL
        msg['Subject'] = f'🚨 SeaVPN: Сервис {service_name} упал!'
        
        body = f"""
🚨 ВНИМАНИЕ! Сервис SeaVPN упал!

📋 Сервис: {service_name}
⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📊 Статус: {status}

📝 Последние логи:
{logs}

🔧 Рекомендуемые действия:
1. Проверить логи: journalctl -u {service_name} -f
2. Перезапустить сервис: systemctl restart {service_name}
3. Проверить ресурсы сервера: htop, df -h

---
SeaVPN Service Monitor
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Отправляем через локальный postfix
        with smtplib.SMTP('localhost') as server:
            server.send_message(msg)
        
        logging.info(f"Email уведомление отправлено для {service_name}")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка отправки email для {service_name}: {e}")
        return False

def send_telegram_notification(service_name, status, logs):
    """Отправляет уведомление в Telegram"""
    try:
        message = f"""
🚨 **SeaVPN: Сервис упал!**

📋 **Сервис:** `{service_name}`
⏰ **Время:** {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
📊 **Статус:** {status}

📝 **Последние логи:**
```
{logs[:1000]}...
```

🔧 **Рекомендуемые действия:**
1. Проверить логи: `journalctl -u {service_name} -f`
2. Перезапустить: `systemctl restart {service_name}`
3. Проверить ресурсы: `htop`, `df -h`

---
SeaVPN Service Monitor
        """
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': ADMIN_TELEGRAM_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        
        logging.info(f"Telegram уведомление отправлено для {service_name}")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка отправки Telegram для {service_name}: {e}")
        return False

def monitor_services():
    """Основная функция мониторинга"""
    logging.info("Запуск мониторинга сервисов SeaVPN...")
    
    while True:
        try:
            for service in SERVICES:
                current_status = check_service_status(service)
                
                # Проверяем, изменился ли статус
                if service not in service_states:
                    service_states[service] = current_status
                    logging.info(f"Инициализация сервиса {service}: {'активен' if current_status else 'неактивен'}")
                    continue
                
                previous_status = service_states[service]
                
                # Если сервис упал
                if previous_status and not current_status:
                    logging.warning(f"🚨 Сервис {service} упал!")
                    
                    # Получаем логи
                    logs = get_service_logs(service)
                    
                    # Отправляем уведомления
                    if ENABLE_EMAIL_NOTIFICATIONS:
                        send_email_notification(service, "Упал", logs)
                    send_telegram_notification(service, "Упал", logs)
                    
                    # Обновляем состояние
                    service_states[service] = current_status
                
                # Если сервис восстановился
                elif not previous_status and current_status:
                    logging.info(f"✅ Сервис {service} восстановился!")
                    
                    # Отправляем уведомление о восстановлении
                    recovery_message = f"✅ Сервис {service} восстановлен в {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                    
                    try:
                        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                        data = {
                            'chat_id': ADMIN_TELEGRAM_ID,
                            'text': recovery_message,
                            'parse_mode': 'Markdown'
                        }
                        requests.post(url, data=data, timeout=10)
                    except:
                        pass
                    
                    service_states[service] = current_status
            
            # Пауза между проверками (30 секунд)
            time.sleep(30)
            
        except KeyboardInterrupt:
            logging.info("Мониторинг остановлен пользователем")
            break
        except Exception as e:
            logging.error(f"Ошибка в мониторинге: {e}")
            time.sleep(60)  # Пауза при ошибке

if __name__ == "__main__":
    # Создаем директорию для логов
    os.makedirs('/var/log/seavpn', exist_ok=True)
    
    # Запускаем мониторинг
    monitor_services()
