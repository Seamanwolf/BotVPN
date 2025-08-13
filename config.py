import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Токен бота
BOT_TOKEN = "8394863099:AAGQ3w7Y7WnYr9kfji_UcFc3jV-I--TIIvQ"

# 3xUI Configuration
XUI_BASE_URL = os.getenv("XUI_BASE_URL", "nl.universaltools.pro")
XUI_PORT = os.getenv("XUI_PORT", "34235")
XUI_WEBBASEPATH = os.getenv("XUI_WEBBASEPATH", "CVbzPVZjXGDiTsw")
XUI_USERNAME = os.getenv("XUI_USERNAME", "XBYiLVDMb5")
XUI_PASSWORD = os.getenv("XUI_PASSWORD", "zclNU7rzrF")

# Тарифы
TARIFFS = {
    "1m": {
        "price": 149,
        "days": 30,
        "name": "1 месяц"
    },
    "3m": {
        "price": 399,
        "days": 90,
        "name": "3 месяца"
    },
    "test": {
        "price": 0,
        "days": 1,
        "name": "Тест (1 день)"
    }
}

# Реферальная система
REFERRAL_BONUS = 150  # Бонус за приглашение
BONUS_TO_SUBSCRIPTION = 150  # Монет за 1 месяц подписки

# Поддержка
SUPPORT_BOT = "@seavpn_support"

# Администраторы
ADMIN_IDS = [261337953]  # Список Telegram ID администраторов
ADMIN_WEB_USERNAME = "Admin"
ADMIN_WEB_PASSWORD = "CegthGfzkmybr72"

# Уведомления для администраторов
ADMIN_NOTIFICATIONS_ENABLED = True  # Включены ли уведомления по умолчанию
