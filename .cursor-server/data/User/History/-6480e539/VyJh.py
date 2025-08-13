import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = "8394863099:AAGQ3w7Y7WnYr9kfji_UcFc3jV-I--TIIvQ"

# 3xUI Configuration
XUI_BASE_URL = os.getenv("XUI_BASE_URL", "")
XUI_USERNAME = os.getenv("XUI_USERNAME", "admin")
XUI_PASSWORD = os.getenv("XUI_PASSWORD", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/vpn_bot")

# Tariffs
TARIFFS = {
    "1m": {"name": "1 месяц", "price": 149, "months": 1},
    "3m": {"name": "3 месяца", "price": 399, "months": 3}
}
