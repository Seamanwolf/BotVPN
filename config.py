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
        "name": "1 месяц",
        "description": "• Доступ на 30 дней\n• Можно использовать на 3 устройствах\n• Уведомления за 3 дня до истечения\n• Техническая поддержка 24/7"
    },
    "3m": {
        "price": 399,
        "days": 90,
        "name": "3 месяца",
        "description": "• Доступ на 90 дней\n• Можно использовать на 3 устройствах\n• Уведомления за 3 дня до истечения\n• Техническая поддержка 24/7\n• Экономия 48₽ по сравнению с месячными тарифами"
    },
    "test": {
        "price": 1,
        "days": 1,
        "name": "Тест (1 день)",
        "description": "• Тестовый доступ на 1 день\n• Можно использовать на 1 устройстве\n• Полный функционал для тестирования"
    }
}

# Корпоративные тарифы
CORPORATE_TARIFFS = {
    "1m": {
        "base_price_per_user": 200,  # Базовая цена за пользователя в месяц
        "days": 30,
        "name": "Корпоративный 1 месяц",
        "description": "• Минимум 5 пользователей\n• Максимум 20 пользователей\n• 1 устройство на пользователя\n• Уведомления за 3 дня до истечения\n• Приоритетная техническая поддержка\n• Скидка при большем количестве пользователей"
    },
    "3m": {
        "base_price_per_user": 180,  # Базовая цена за пользователя в месяц (скидка)
        "days": 90,
        "name": "Корпоративный 3 месяца",
        "description": "• Минимум 5 пользователей\n• Максимум 20 пользователей\n• 1 устройство на пользователя\n• Уведомления за 3 дня до истечения\n• Приоритетная техническая поддержка\n• Максимальная скидка при большем количестве пользователей"
    }
}

# Функция для расчета стоимости корпоративного тарифа
def calculate_corporate_price(users_count: int, tariff_type: str) -> int:
    """
    Рассчитывает стоимость корпоративного тарифа с учетом скидок
    
    Args:
        users_count: Количество пользователей (5, 10, 15, 20)
        tariff_type: Тип тарифа ("1m" или "3m")
    
    Returns:
        Общая стоимость в рублях
    """
    if users_count not in [5, 10, 15, 20]:
        raise ValueError("Количество пользователей должно быть 5, 10, 15 или 20")
    
    base_price = CORPORATE_TARIFFS[tariff_type]["base_price_per_user"]
    
    # Применяем скидки в зависимости от количества пользователей
    if users_count >= 15:
        discount = 0.15  # 15% скидка для 15+ пользователей
    elif users_count >= 10:
        discount = 0.10  # 10% скидка для 10+ пользователей
    else:
        discount = 0.0  # Без скидки для 5 пользователей
    
    total_price = int(users_count * base_price * (1 - discount))
    return total_price

# Реферальная система
REFERRAL_BONUS = 50  # Бонус за приглашение
BONUS_TO_SUBSCRIPTION = 150  # Монет за 1 месяц подписки

# Поддержка
SUPPORT_BOT = "@seavpn_support"

# Администраторы
ADMIN_IDS = [261337953]  # Список Telegram ID администраторов
ADMIN_WEB_USERNAME = "Admin"
ADMIN_WEB_PASSWORD = "CegthGfzkmybr72"

# Уведомления для администраторов
ADMIN_NOTIFICATIONS_ENABLED = True  # Включены ли уведомления по умолчанию

# ЮKassa Configuration
YOOKASSA_SECRET_KEY = "live_QMWqzDoOaDHGhRW5vlfU9nNM8rRdjStxe1pUayD_30w"
YOOKASSA_SHOP_ID = "1141477"  # Shop ID из личного кабинета ЮKassa
