import asyncio
from datetime import datetime, timedelta
from database import SessionLocal, User, Subscription, AdminSettings
from config import BOT_TOKEN
from aiogram import Bot
import os
import requests

INTERNAL_NOTIFY_URL = os.getenv("INTERNAL_NOTIFY_URL", "http://127.0.0.1:8080/internal/notify")

class NotificationManager:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.running = False
    
    async def start(self):
        """Запуск менеджера уведомлений"""
        self.running = True
        asyncio.create_task(self.check_expiring_subscriptions())
    
    async def stop(self):
        """Остановка менеджера уведомлений"""
        self.running = False
    
    async def check_expiring_subscriptions(self):
        """Проверка истекающих подписок"""
        while self.running:
            try:
                db = SessionLocal()
                try:
                    # Получаем подписки, которые истекают в ближайшие 3 дня
                    three_days_from_now = datetime.utcnow() + timedelta(days=3)
                    expiring_subscriptions = db.query(Subscription).filter(
                        Subscription.status == "active",
                        Subscription.expires_at <= three_days_from_now,
                        Subscription.expires_at > datetime.utcnow()
                    ).all()
                    
                    for subscription in expiring_subscriptions:
                        user = db.query(User).filter(User.id == subscription.user_id).first()
                        if user:
                            await self.send_expiry_notification(user, subscription)
                    
                finally:
                    db.close()
                
                # Проверяем каждые 12 часов
                await asyncio.sleep(12 * 60 * 60)
                
            except Exception as e:
                print(f"Ошибка в check_expiring_subscriptions: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повторной попыткой
    
    async def send_expiry_notification(self, user: User, subscription: Subscription):
        """Отправка уведомления об истечении подписки"""
        try:
            days_left = (subscription.expires_at - datetime.utcnow()).days
            
            if days_left == 0:
                message = f"⚠️ **Ваша подписка истекает сегодня!**\n\n"
            elif days_left == 1:
                message = f"⚠️ **Ваша подписка истекает завтра!**\n\n"
            else:
                message = f"⚠️ **Ваша подписка истекает через {days_left} дня!**\n\n"
            
            message += f"📦 Тариф: {subscription.plan_name}\n"
            message += f"📅 Дата истечения: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
            
            # Создаем клавиатуру с кнопками продления
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard_buttons = []
            
            # Кнопки для оплаты
            money_row = []
            money_row.append(InlineKeyboardButton(text="💳 Продлить на 1 месяц (149₽)", callback_data=f"extend_1m_{subscription.id}"))
            money_row.append(InlineKeyboardButton(text="💳 Продлить на 3 месяца (399₽)", callback_data=f"extend_3m_{subscription.id}"))
            keyboard_buttons.append(money_row)
            
            # Кнопки для бонусных монет (если у пользователя достаточно монет)
            if user.bonus_coins >= 150:
                bonus_row = []
                if user.bonus_coins >= 150:
                    bonus_row.append(InlineKeyboardButton(text="🪙 Продлить на 1 месяц (150 монет)", callback_data=f"extend_bonus_1m_{subscription.id}"))
                if user.bonus_coins >= 450:
                    bonus_row.append(InlineKeyboardButton(text="🪙 Продлить на 3 месяца (450 монет)", callback_data=f"extend_bonus_3m_{subscription.id}"))
                if bonus_row:
                    keyboard_buttons.append(bonus_row)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка при отправке уведомления об истечении: {e}")
    
    async def notify_referral_bonus(self, referrer_id: int, new_user_name: str):
        """Уведомление о реферальном бонусе"""
        try:
            from config import REFERRAL_BONUS
            
            message = (
                f"🎁 **Реферальный бонус!**\n\n"
                f"Пользователь {new_user_name} совершил первую покупку по вашей реферальной ссылке!\n\n"
                f"💰 Вам начислено: {REFERRAL_BONUS} монет\n\n"
                f"💡 Используйте монеты для покупки подписок в разделе 'Реферальная система'"
            )
            
            await self.bot.send_message(
                chat_id=referrer_id,
                text=message,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            print(f"Ошибка при отправке уведомления о реферальном бонусе: {e}")
    
    async def notify_coins_added(self, user, coins_amount: int):
        """Уведомление пользователя о начислении бонусных монет"""
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            message = f"🎁 **Вам начислены бонусные монеты!**\n\n"
            message += f"💰 **Количество:** {coins_amount} 🪙\n"
            message += f"💼 **Текущий баланс:** {user.bonus_coins} 🪙\n\n"
            message += f"💎 Вы можете использовать монеты для покупки подписки:\n"
            message += f"• 150 монет = 1 месяц подписки\n"
            message += f"• 450 монет = 3 месяца подписки\n\n"
            message += f"⏰ **Время начисления:** {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}"
            
            # Создаем клавиатуру с кнопками для покупки подписки
            keyboard_buttons = []
            
            # Кнопки для бонусных монет (если у пользователя достаточно монет)
            if user.bonus_coins >= 150:
                bonus_row = []
                if user.bonus_coins >= 150:
                    bonus_row.append(InlineKeyboardButton(text="🪙 Купить 1 месяц за 150 монет", callback_data="buy_bonus_1m"))
                if user.bonus_coins >= 450:
                    bonus_row.append(InlineKeyboardButton(text="🪙 Купить 3 месяца за 450 монет", callback_data="buy_bonus_3m"))
                if bonus_row:
                    keyboard_buttons.append(bonus_row)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
        except Exception as e:
            print(f"Ошибка при отправке уведомления о начислении монет: {e}")
    
    async def notify_admin_new_purchase(self, user, subscription, payment_amount: int):
        """Уведомление администраторов о новой покупке"""
        try:
            # Получаем ID администраторов из конфигурации
            from config import ADMIN_IDS
            
            message = f"🛒 **Новая покупка!**\n\n"
            message += f"👤 **Пользователь:** {user.full_name or 'Не указано'}\n"
            message += f"🆔 **Telegram ID:** {user.telegram_id}\n"
            message += f"📧 **Email:** {user.email or 'Не указан'}\n\n"
            message += f"📦 **Тариф:** {subscription.plan_name}\n"
            message += f"💰 **Сумма:** {payment_amount}₽\n"
            message += f"📅 **Действует до:** {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
            message += f"🔑 **Ключ:** SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number}\n\n"
            message += f"⏰ **Время покупки:** {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}"
            
            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Ошибка при отправке уведомления админу {admin_id}: {e}")
                    
        except Exception as e:
            print(f"Ошибка при отправке уведомления о новой покупке: {e}")
    
    async def notify_admin_extension(self, user, subscription, payment_amount: int, days_added: int):
        """Уведомление администраторов о продлении подписки"""
        try:
            # Получаем всех активных администраторов
            db = SessionLocal()
            try:
                from database import Admin
                admins = db.query(Admin).filter(Admin.is_active == True).all()
            finally:
                db.close()
            
            message = f"🔄 **Продление подписки!**\n\n"
            message += f"👤 **Пользователь:** {user.full_name or 'Не указано'}\n"
            message += f"🆔 **Telegram ID:** {user.telegram_id}\n"
            message += f"📧 **Email:** {user.email or 'Не указан'}\n\n"
            message += f"📦 **Тариф:** {subscription.plan_name}\n"
            message += f"💰 **Сумма:** {payment_amount}₽\n"
            message += f"⏰ **Добавлено дней:** {days_added}\n"
            message += f"📅 **Новая дата окончания:** {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
            message += f"🔑 **Ключ:** SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number}\n\n"
            message += f"⏰ **Время продления:** {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}"
            
            for admin in admins:
                try:
                    await self.bot.send_message(
                        chat_id=admin.telegram_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Ошибка при отправке уведомления админу {admin.telegram_id}: {e}")
                    
        except Exception as e:
            print(f"Ошибка при отправке уведомления о продлении: {e}")

# Глобальный экземпляр менеджера уведомлений
notification_manager = None

async def run_notification_scheduler():
    """Запуск планировщика уведомлений"""
    global notification_manager
    notification_manager = NotificationManager()
    await notification_manager.start()

def get_admin_settings():
    """Получение настроек администратора"""
    db = SessionLocal()
    try:
        settings = db.query(AdminSettings).first()
        if not settings:
            settings = AdminSettings()
            db.add(settings)
            db.commit()
        return settings
    finally:
        db.close()

def update_admin_settings(notifications_enabled=None, new_user_notifications=None, subscription_notifications=None):
    """Обновление настроек администратора"""
    db = SessionLocal()
    try:
        settings = db.query(AdminSettings).first()
        if not settings:
            settings = AdminSettings()
            db.add(settings)
        
        if notifications_enabled is not None:
            settings.notifications_enabled = notifications_enabled
        if new_user_notifications is not None:
            settings.new_user_notifications = new_user_notifications
        if subscription_notifications is not None:
            settings.subscription_notifications = subscription_notifications
        
        db.commit()
        return settings
    finally:
        db.close()

async def send_admin_notification(message: str):
    """Отправка уведомления администраторам"""
    try:
        from config import ADMIN_IDS
        
        bot = Bot(token=BOT_TOKEN)
        
        # Отправляем всем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Ошибка отправки уведомления администратору {admin_id}: {e}")
        
        await bot.session.close()
        
    except Exception as e:
        print(f"Ошибка при отправке уведомления администраторам: {e}")

def notify_new_message(ticket_id: str, message_id: str, preview: str, author: str):
    """
    Вызывать сразу после сохранения сообщения в тикете.
    Если бот/обработчик работает в другом процессе или контейнере — стучимся HTTP.
    Если в одном процессе — можешь вместо HTTP импортировать socketio и emit-ить напрямую.
    """
    try:
        requests.post(
            INTERNAL_NOTIFY_URL,
            json={
                "ticket_id": str(ticket_id),
                "message_id": str(message_id),
                "preview": preview or "",
                "author": author or "",
            },
            timeout=3,
        )
    except Exception as e:
        # Не роняем поток — логируй по месту
        print(f"[notify] failed: {e}")

def notify_new_user(user_id: str, full_name: str, phone: str, email: str):
    """
    Вызывать сразу после регистрации нового пользователя.
    """
    try:
        requests.post(
            INTERNAL_NOTIFY_URL,
            json={
                "type": "new_user",
                "user_id": str(user_id),
                "full_name": full_name or "",
                "phone": phone or "",
                "email": email or "",
            },
            timeout=3,
        )
    except Exception as e:
        # Не роняем поток — логируй по месту
        print(f"[notify] failed: {e}") 