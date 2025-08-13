import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = "8394863099:AAGQ3w7Y7WnYr9kfji_UcFc3jV-I--TIIvQ"

# 3xUI Configuration
XUI_BASE_URL = os.getenv("XUI_BASE_URL")
XUI_PORT = os.getenv("XUI_PORT")
XUI_WEBBASEPATH = os.getenv("XUI_WEBBASEPATH")
XUI_USERNAME = os.getenv("XUI_USERNAME")
XUI_PASSWORD = os.getenv("XUI_PASSWORD")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/vpn_bot")

# Tariffs
TARIFFS = {
    "1m": {"name": "1 месяц", "price": 149, "months": 1},
    "3m": {"name": "3 месяца", "price": 399, "months": 3}
}

# Referral system
REFERRAL_BONUS = 50  # Бонус за приглашение (монеты)
BONUS_TO_SUBSCRIPTION = 150  # Сколько монет нужно для обмена на месяц подписки
SUPPORT_BOT = "SeaVPN_support_bot"

# Admin configuration
ADMIN_IDS = [261337953]  # Список Telegram ID администраторов
ADMIN_WEB_USERNAME = "Admin"
ADMIN_WEB_PASSWORD = "CegthGfzkmybr72"
