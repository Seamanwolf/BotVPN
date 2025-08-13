# BotVPN - Telegram Bot для управления VPN подписками

Telegram бот для управления VPN подписками с интеграцией 3xUI панели, YooMoney платежей и веб-админ панелью.

## 🚀 Возможности

### Telegram Bot
- 📱 Регистрация пользователей через Telegram
- 💳 Покупка подписок через YooMoney
- 🎁 Реферальная система с бонусными монетами
- 🔄 Автоматическое создание конфигураций в 3xUI
- ⏰ Уведомления об истечении подписки
- 🎯 Админ-кнопки для управления ботом

### Веб-админ панель
- 📊 Дашборд со статистикой
- 👥 Управление пользователями
- 📦 Управление подписками
- 👨‍💼 Управление администраторами
- ⚙️ Настройки уведомлений
- 🌙 Темная/светлая тема

### Интеграции
- 🔗 3xUI панель для VPN конфигураций
- 💰 YooMoney для приема платежей
- 🗄️ PostgreSQL база данных
- 🔔 Telegram уведомления

## 🛠️ Технологии

- **Backend:** Python 3.10+, Flask, SQLAlchemy
- **Telegram Bot:** aiogram 3.x
- **Database:** PostgreSQL
- **Frontend:** Bootstrap 5, JavaScript
- **Payments:** YooMoney API
- **VPN:** 3xUI API

## 📋 Требования

- Python 3.10+
- PostgreSQL
- 3xUI панель
- YooMoney аккаунт
- Telegram Bot Token

## 🚀 Установка

### 1. Клонирование репозитория
```bash
git clone https://github.com/Seamanwolf/BotVPN.git
cd BotVPN
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка базы данных
```bash
# Создание базы данных PostgreSQL
createdb vpn_bot
```

### 4. Настройка переменных окружения
Создайте файл `.env`:
```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://user:password@localhost/vpn_bot
YOO_MONEY_TOKEN=your_yoomoney_token
XUI_BASE_URL=your_3xui_server
XUI_PORT=54321
XUI_USERNAME=admin
XUI_PASSWORD=your_password
XUI_WEBBASEPATH=your_webpath
```

### 5. Инициализация базы данных
```bash
python3 -c "from database import Base, engine; Base.metadata.create_all(engine)"
```

### 6. Создание супер-админа
```bash
python3 create_superadmin.py
```

## 🏃‍♂️ Запуск

### Telegram Bot
```bash
python3 bot.py
```

### Веб-админ панель
```bash
python3 admin_web.py
```

### Системные сервисы (systemd)
```bash
# Копирование сервисных файлов
sudo cp systemd/seavpn-bot.service /etc/systemd/system/
sudo cp systemd/seavpn-admin.service /etc/systemd/system/

# Включение и запуск сервисов
sudo systemctl enable seavpn-bot
sudo systemctl enable seavpn-admin
sudo systemctl start seavpn-bot
sudo systemctl start seavpn-admin
```

## 📁 Структура проекта

```
BotVPN/
├── bot.py                 # Основной Telegram бот
├── admin_web.py           # Веб-админ панель
├── database.py            # Модели базы данных
├── config.py              # Конфигурация
├── xui_client.py          # Клиент для 3xUI API
├── notifications.py       # Система уведомлений
├── templates/             # HTML шаблоны
│   ├── base.html
│   ├── dashboard.html
│   ├── users.html
│   ├── subscriptions.html
│   ├── admins.html
│   └── login.html
├── static/                # Статические файлы
├── systemd/               # Systemd сервисы
├── requirements.txt       # Python зависимости
└── README.md
```

## 🔧 Конфигурация

### Тарифы
Настройте тарифы в `config.py`:
```python
TARIFFS = {
    "1m": {"price": 299, "days": 30, "name": "1 месяц"},
    "3m": {"price": 799, "days": 90, "name": "3 месяца"},
    "test": {"price": 0, "days": 1, "name": "Тест (1 день)"}
}
```

### Реферальная система
```python
REFERRAL_BONUS = 150  # Бонусные монеты за реферала
```

## 📊 API Endpoints

### Веб-админ панель
- `GET /` - Главная страница
- `GET /users` - Управление пользователями
- `GET /subscriptions` - Управление подписками
- `GET /admins` - Управление администраторами
- `GET /settings` - Настройки

### API для управления
- `POST /api/user/{id}/delete` - Удаление пользователя
- `POST /api/subscription/{id}/pause` - Приостановка подписки
- `POST /api/admin/add` - Добавление администратора

## 🔒 Безопасность

- Аутентификация через Telegram ID
- Хеширование паролей (bcrypt)
- Валидация входных данных
- Защита от SQL-инъекций
- HTTPS для веб-панели

## 📝 Лицензия

MIT License

## 🤝 Поддержка

Для получения поддержки создайте Issue в GitHub репозитории.

## 📈 Планы развития

- [ ] Мобильное приложение
- [ ] Многоязычная поддержка
- [ ] Интеграция с другими платежными системами
- [ ] Расширенная аналитика
- [ ] API для внешних интеграций
