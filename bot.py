import asyncio
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json


from config import BOT_TOKEN, TARIFFS, CORPORATE_TARIFFS, calculate_corporate_price, REFERRAL_BONUS, BONUS_TO_SUBSCRIPTION, SUPPORT_BOT, ADMIN_IDS
from database import SessionLocal, User, Subscription, Admin, AdminSettings, Payment, generate_referral_code, get_user_by_referral_code, check_telegram_id_exists
from xui_client import XUIClient
from yookassa_client import YooKassaClient
from notifications import NotificationManager, run_notification_scheduler

# Состояния для FSM


class CorporateStates(StatesGroup):
    waiting_for_users_count = State()

class NotificationStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_message = State()
    waiting_for_recipient_type = State()

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Клиент 3xUI
xui_client = XUIClient()

# Клиент ЮKassa
yookassa_client = YooKassaClient()

# Менеджер уведомлений
notification_manager = None





def get_main_menu_keyboard(is_admin=False):
    """Главное меню"""
    keyboard_buttons = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🔑 Мои ключи")],
        [KeyboardButton(text="💳 Купить ключ"), KeyboardButton(text="🎁 Реферальная система")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="🚀 Почему наш VPN?")]
    ]
    
    # Добавляем кнопку админки для администраторов
    if is_admin:
        keyboard_buttons.append([KeyboardButton(text="⚙️ Админ-панель")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True
    )
    return keyboard

def get_tariffs_keyboard(is_admin=False):
    """Клавиатура с тарифами"""
    keyboard_buttons = [
        [KeyboardButton(text=f"1 месяц - {TARIFFS['1m']['price']}₽")],
        [KeyboardButton(text=f"3 месяца - {TARIFFS['3m']['price']}₽")],
        [KeyboardButton(text="🏢 Корпоративные ключи")],
        [KeyboardButton(text="Назад")]
    ]
    
    # Добавляем кнопку тестового тарифа только для администраторов
    if is_admin:
        keyboard_buttons.insert(2, [KeyboardButton(text="Купить тест (1 день)")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True
    )
    return keyboard

def get_corporate_keyboard(is_admin=False):
    """Клавиатура с корпоративными тарифами"""
    keyboard_buttons = [
        [KeyboardButton(text="🏢 Корпоративный 1 месяц")],
        [KeyboardButton(text="🏢 Корпоративный 3 месяца")]
    ]
    
    # Добавляем тестовую кнопку только для админа
    if is_admin:
        keyboard_buttons.append([KeyboardButton(text="🧪 Тест корпоративный (1 рубль)")])
    
    keyboard_buttons.append([KeyboardButton(text="Назад")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True
    )
    return keyboard



# Получение пользователя из БД
async def get_user(telegram_id: int) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        return user
    finally:
        db.close()

# Проверка является ли пользователь администратором
def is_admin(telegram_id: int) -> bool:
    # Сначала проверяем старый способ (для совместимости)
    if telegram_id in ADMIN_IDS:
        return True
    
    # Затем проверяем в базе данных
    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(
            Admin.telegram_id == telegram_id,
            Admin.is_active == True
        ).first()
        return admin is not None
    finally:
        db.close()

# Получение клавиатуры с учетом админ-статуса
def get_user_keyboard(telegram_id: int):
    return get_main_menu_keyboard(is_admin=is_admin(telegram_id))

def get_admin_notifications_keyboard():
    """Клавиатура для управления уведомлениями"""
    keyboard = [
        [
            InlineKeyboardButton(text="🔔 Включить", callback_data="notifications_on"),
            InlineKeyboardButton(text="🔕 Отключить", callback_data="notifications_off")
        ],
        [InlineKeyboardButton(text="📊 Статус", callback_data="notifications_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_extend_keyboard(subscription_id: int, user_bonus_coins: int) -> InlineKeyboardMarkup:
    """Создает inline клавиатуру для продления подписки"""
    keyboard_buttons = []
    
    # Кнопка тестового продления за 1 рубль
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=f"🧪 Продлить тест ({TARIFFS['test']['price']}₽)",
            callback_data=f"extend_paid_{subscription_id}_test"
        )
    ])
    
    # Кнопка продления на 1 месяц за деньги
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=f"💳 Продлить на 1 месяц ({TARIFFS['1m']['price']}₽)",
            callback_data=f"extend_paid_{subscription_id}_1m"
        )
    ])
    
    # Кнопка продления на 3 месяца за деньги
    keyboard_buttons.append([
        InlineKeyboardButton(
            text=f"💳 Продлить на 3 месяца ({TARIFFS['3m']['price']}₽)",
            callback_data=f"extend_paid_{subscription_id}_3m"
        )
    ])
    
    # Кнопки продления за бонусы (если достаточно монет)
    if user_bonus_coins >= BONUS_TO_SUBSCRIPTION:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"💎 Продлить на 1 месяц ({BONUS_TO_SUBSCRIPTION} монет)",
                callback_data=f"extend_bonus_{subscription_id}_1m"
            )
        ])
    
    if user_bonus_coins >= BONUS_TO_SUBSCRIPTION * 3:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"💎 Продлить на 3 месяца ({BONUS_TO_SUBSCRIPTION * 3} монет)",
                callback_data=f"extend_bonus_{subscription_id}_3m"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

# Функции для работы с уведомлениями администраторов
def get_admin_settings():
    """Получение настроек уведомлений администраторов"""
    db = SessionLocal()
    try:
        settings = db.query(AdminSettings).first()
        if not settings:
            # Создаем настройки по умолчанию
            settings = AdminSettings()
            db.add(settings)
            db.commit()
        return settings
    finally:
        db.close()

def update_admin_settings(notifications_enabled=None, new_user_notifications=None, subscription_notifications=None):
    """Обновление настроек уведомлений администраторов"""
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
    """Отправка уведомления всем администраторам"""
    settings = get_admin_settings()
    if not settings.notifications_enabled:
        return
    
    db = SessionLocal()
    try:
        admins = db.query(Admin).filter(Admin.is_active == True).all()
        for admin in admins:
            try:
                await bot.send_message(admin.telegram_id, message)
            except Exception as e:
                print(f"Ошибка отправки уведомления админу {admin.telegram_id}: {e}")
    finally:
        db.close()

# Сохранение пользователя в БД
async def save_user(telegram_id: int, full_name: str, referral_code: str = None) -> User:
    db = SessionLocal()
    try:
        # Проверяем уникальность Telegram ID
        if check_telegram_id_exists(telegram_id):
            raise ValueError(f"Пользователь с Telegram ID {telegram_id} уже существует")
        

        
        # Генерируем уникальный реферальный код
        user_referral_code = generate_referral_code()
        
        # Проверяем, есть ли реферальный код
        referred_by = None
        if referral_code:
            referrer = get_user_by_referral_code(referral_code)
            if referrer:
                referred_by = referrer.id
        
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            referral_code=user_referral_code,
            referred_by=referred_by
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Бонусы за рефералов начисляются только при первой покупке, а не при регистрации
        
        return user
    except ValueError as e:
        db.rollback()
        raise e
    finally:
        db.close()

# Обработчик команды /start
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    # Очищаем состояние FSM при старте
    await state.clear()
    
    user = await get_user(message.from_user.id)
    
    if user:
        # Пользователь уже зарегистрирован
        await message.answer(
            f"С возвращением, {user.full_name}! 👋\n\nВыберите действие:",
            reply_markup=get_main_menu_keyboard(is_admin=is_admin(user.telegram_id))
        )
    else:
        # Новая регистрация
        # Проверяем, есть ли реферальный код в команде
        referral_code = None
        if len(message.text.split()) > 1:
            referral_code = message.text.split()[1]
        
        # Получаем имя из профиля Telegram
        full_name = message.from_user.full_name or message.from_user.first_name or f"Пользователь {message.from_user.id}"
        
        # Сохраняем пользователя сразу
        try:
            user = await save_user(message.from_user.id, full_name, referral_code)
        
        await message.answer(
            f"Регистрация завершена! 🎉\n\nДобро пожаловать, {full_name}!\n\nВыберите действие:",
            reply_markup=get_user_keyboard(message.from_user.id)
        )
        
        # Отправляем уведомление администраторам о новом пользователе
        settings = get_admin_settings()
        if settings.notifications_enabled and settings.new_user_notifications:
            notification_text = (
                f"🆕 **Новый пользователь зарегистрировался!**\n\n"
                f"👤 Имя: {full_name}\n"
                f"🆔 Telegram ID: {message.from_user.id}\n"
                f"🎁 Бонусные монеты: {user.bonus_coins}\n"
                f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            await send_admin_notification(notification_text)
            
            # Отправляем уведомление через Socket.IO
            try:
                from notifications import notify_new_user
                    notify_new_user(str(user.id), full_name, "", "")
            except Exception as e:
                print(f"Ошибка при отправке Socket.IO уведомления о новом пользователе: {e}")
    except ValueError as e:
        await message.answer(
            f"❌ Ошибка регистрации: {str(e)}\n\nПопробуйте еще раз или обратитесь в поддержку.",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True)
        )

# Команда для отправки массовых уведомлений (только для админов)
@dp.message(F.text == "/send_notification")
async def send_notification_command(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам.")
        return
    
    await state.set_state(NotificationStates.waiting_for_title)
    await message.answer(
        "📢 <b>Отправка массового уведомления</b>\n\n"
        "Введите заголовок уведомления (будет отображаться жирным шрифтом):",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    )



# Обработчик главного меню
@dp.message(F.text.in_(["👤 Профиль", "🔑 Мои ключи", "💳 Купить ключ", "🎁 Реферальная система", "❓ Помощь", "⚙️ Админ-панель", "📋 Получить ссылку для копирования", "🚀 Почему наш VPN?"]))
async def main_menu_handler(message: Message):
    user = await get_user(message.from_user.id)
    
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    if message.text == "👤 Профиль":
        # Получаем активную подписку
        db = SessionLocal()
        try:
            active_subscription = db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.status == "active"
            ).first()
            
            subscription_info = ""
            if active_subscription:
                expires = active_subscription.expires_at.strftime("%d.%m.%Y")
                subscription_info = f"\nАктивная подписка до: {expires}"
            else:
                subscription_info = "\nАктивная подписка: нет"
                
        finally:
            db.close()
        
        await message.answer(
            f"📋 Профиль\n\n"
            f"Имя: {user.full_name}\n"
            f"Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}\n"
            f"Бонусные монеты: {user.bonus_coins} 🪙"
            f"{subscription_info}",
            reply_markup=get_user_keyboard(message.from_user.id)
        )
    
    elif message.text == "🔑 Мои ключи":
        # Получаем все активные подписки и конфигурации
        db = SessionLocal()
        try:
            # Получаем только действительно активные подписки (не истекшие)
            current_time = datetime.utcnow()
            active_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.status == "active",
                Subscription.expires_at > current_time
            ).order_by(Subscription.subscription_number).all()
            
            if active_subscriptions:
                configs_found = 0
                
                for subscription in active_subscriptions:
                    # Получаем актуальную конфигурацию из 3xUI по уникальному email
                    unique_email = f"SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number}"
                    try:
                        config = await xui_client.get_user_config(unique_email, subscription.subscription_number)
                    except Exception as e:
                        print(f"Ошибка при получении конфигурации: {e}")
                        config = None
                    
                    if config:
                        configs_found += 1
                        # Более точный расчет оставшегося времени
                        time_left = subscription.expires_at - current_time
                        days_left = time_left.days
                        hours_left = time_left.seconds // 3600
                        
                        # Формируем сообщение для каждого ключа
                        key_message = f"**Подписка #{subscription.subscription_number}**\n"
                        key_message += f"Тариф: {subscription.plan_name}\n"
                        key_message += f"Действует до: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
                        
                        if days_left <= 0 and hours_left <= 0:
                            key_message += f"⚠️ Подписка истекает сегодня!\n"
                        elif days_left <= 0:
                            key_message += f"⚠️ Подписка истекает через {hours_left} часов!\n"
                        elif days_left <= 3:
                            key_message += f"⚠️ Подписка истекает через {days_left} дней!\n"
                        elif days_left <= 7:
                            key_message += f"📅 Подписка истекает через {days_left} дней\n"
                        else:
                            key_message += f"✅ Подписка активна\n"
                        
                        key_message += f"Конфигурация:\n`{config}`\n"
                        
                        # Создаем клавиатуру для продления
                        extend_keyboard = get_subscription_extend_keyboard(subscription.id, user.bonus_coins)
                        
                        # Отправляем сообщение с кнопками продления
                        await message.answer(
                            key_message,
                            parse_mode="Markdown",
                            reply_markup=extend_keyboard
                        )
                
                if configs_found > 0:
                    # Отправляем общий заголовок
                    await message.answer(
                        "🔑 Ваши ключи\n\nВыберите ключ для продления:",
                        reply_markup=get_user_keyboard(message.from_user.id)
                    )
                else:
                    await message.answer(
                        "У вас нет активных ключей.",
                        reply_markup=get_user_keyboard(message.from_user.id)
                    )
            else:
                await message.answer(
                    "У вас нет активных ключей.",
                    reply_markup=get_user_keyboard(message.from_user.id)
                )
        finally:
            db.close()
    
    elif message.text == "💳 Купить ключ":
        await message.answer(
            "💳 Выберите тариф:",
            reply_markup=get_tariffs_keyboard(is_admin(message.from_user.id))
        )
    
    elif message.text == "🎁 Реферальная система":
        # Получаем статистику рефералов
        db = SessionLocal()
        try:
            referrals_count = db.query(User).filter(User.referred_by == user.id).count()
            
            # Получаем username бота
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            
            referral_text = f"🎁 <b>Реферальная система</b>\n\n"
            referral_text += f"Ваш реферальный код: <code>{user.referral_code}</code>\n"
            referral_text += f"Ваша реферальная ссылка (выделите и скопируйте):\n<code>https://t.me/{bot_username}?start={user.referral_code}</code>\n\n"
            referral_text += f"Приглашено пользователей: {referrals_count}\n"
            referral_text += f"Бонусных монет: {user.bonus_coins} 🪙\n\n"
            referral_text += f"💰 За каждого приглашенного пользователя вы получаете {REFERRAL_BONUS} монет\n"
            referral_text += f"💎 {BONUS_TO_SUBSCRIPTION} монет = 1 месяц подписки\n"
            referral_text += f"💎 {BONUS_TO_SUBSCRIPTION * 3} монет = 3 месяца подписки\n\n"
            referral_text += f"📱 <b>Как это работает:</b>\n"
            referral_text += f"1. Отправьте реферальную ссылку друзьям\n"
            referral_text += f"2. Когда ваш друг перейдет по ссылке и совершит первую покупку, вам начислится {REFERRAL_BONUS} монет\n"
            referral_text += f"3. Накопите монеты и обменяйте их на бесплатную подписку\n\n"
            
            # Формируем кнопки в зависимости от количества бонусов
            keyboard_buttons = []
            
            if user.bonus_coins >= BONUS_TO_SUBSCRIPTION * 3:
                keyboard_buttons.append([KeyboardButton(text="🪙 Купить 3 месяца за 450 монет")])
                keyboard_buttons.append([KeyboardButton(text="🪙 Купить 1 месяц за 150 монет")])
            elif user.bonus_coins >= BONUS_TO_SUBSCRIPTION:
                keyboard_buttons.append([KeyboardButton(text="🪙 Купить 1 месяц за 150 монет")])
            else:
                referral_text += f"📈 До обмена на подписку: {BONUS_TO_SUBSCRIPTION - user.bonus_coins} монет"
            
            keyboard_buttons.append([KeyboardButton(text="📋 Получить ссылку для копирования")])
            keyboard_buttons.append([KeyboardButton(text="Назад")])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=keyboard_buttons,
                resize_keyboard=True
            )
            
            await message.answer(
                referral_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        finally:
            db.close()
    
    elif message.text == "📋 Получить ссылку для копирования":
        # Получаем username бота
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        
        # Отправляем только ссылку в отдельном сообщении для удобного копирования
        referral_link = f"https://t.me/{bot_username}?start={user.referral_code}"
        
        await message.answer(
            referral_link
        )
        
        await message.answer(
            "✅ Скопируйте ссылку выше и отправьте друзьям.\nКогда они перейдут по ссылке и совершат первую покупку, вы получите бонусные монеты!"
        )
    
    elif message.text == "🚀 Почему наш VPN?":
        why_vpn_text = "<b>🚀 Почему наш VPN лучший выбор</b>\n\n"
        why_vpn_text += "✅ <b>Умная маршрутизация:</b>\n"
        why_vpn_text += "• Для YouTube и российских сервисов - используются российские серверы, обеспечивая высокую скорость, отсутствие рекламы и релевантные рекомендации\n"
        why_vpn_text += "• Для заблокированных сервисов - европейские серверы с высокой пропускной способностью\n"
        why_vpn_text += "• Для сервисов, доступных только в США - автоматическое подключение к американским серверам\n\n"
        
        why_vpn_text += "✅ <b>Преимущества:</b>\n"
        why_vpn_text += "• Стабильное соединение без разрывов\n"
        why_vpn_text += "• Высокая скорость для стриминга и загрузки файлов\n"
        why_vpn_text += "• Автоматический выбор оптимального сервера\n"
        why_vpn_text += "• Защита от блокировок и слежки\n"
        why_vpn_text += "• Простая настройка на всех устройствах\n\n"
        
        why_vpn_text += "✅ <b>Есть предложения по улучшению?</b>\n"
        why_vpn_text += f"• Напишите нам в бот поддержки: <a href=\"https://t.me/SeaVPN_support_bot\">@SeaVPN_support_bot</a>\n"
        why_vpn_text += "• Мы ценим ваше мнение и постоянно совершенствуем наш сервис!\n"
        
        await message.answer(
            why_vpn_text,
            parse_mode="HTML"
        )
    
    elif message.text == "⚙️ Админ-панель":
        # Проверяем, является ли пользователь администратором
        if not is_admin(message.from_user.id):
            await message.answer(
                "❌ У вас нет доступа к админ-панели.",
                reply_markup=get_user_keyboard(message.from_user.id)
            )
            return
        
        # Получаем статистику
        db = SessionLocal()
        try:
            total_users = db.query(User).count()
            active_subscriptions = db.query(Subscription).filter(Subscription.status == "active").count()
            expired_subscriptions = db.query(Subscription).filter(Subscription.status == "expired").count()
            paused_subscriptions = db.query(Subscription).filter(Subscription.status == "paused").count()
            
            # Получаем информацию об администраторе
            admin = db.query(Admin).filter(Admin.telegram_id == message.from_user.id).first()
            admin_role = "Суперадмин" if admin and admin.is_superadmin else "Администратор"
            
            admin_text = f"⚙️ Админ-панель\n\n"
            admin_text += f"👤 **Ваша роль:** {admin_role}\n\n"
            admin_text += f"📊 **Статистика:**\n"
            admin_text += f"• Всего пользователей: {total_users}\n"
            admin_text += f"• Активных подписок: {active_subscriptions}\n"
            admin_text += f"• Приостановленных: {paused_subscriptions}\n"
            admin_text += f"• Истекших подписок: {expired_subscriptions}\n\n"
            admin_text += f"🌐 **Веб-панель:**\n"
            admin_text += f"• URL: https://admin.universaltools.pro\n"
            admin_text += f"• Логин: {admin.username if admin else 'Admin'}\n"
            admin_text += f"• Пароль: (установлен при создании)\n\n"
            admin_text += f"💡 **Возможности веб-панели:**\n"
            admin_text += f"• Управление пользователями и подписками\n"
            admin_text += f"• Добавление/удаление администраторов\n"
            admin_text += f"• Синхронизация с 3xUI\n"
            admin_text += f"• Детальная статистика и аналитика\n\n"
            admin_text += f"🔔 **Управление уведомлениями:**\n"
            admin_text += f"• /notifications_on - включить уведомления\n"
            admin_text += f"• /notifications_off - отключить уведомления\n"
            admin_text += f"• /notifications_status - статус уведомлений\n\n"
            admin_text += f"Или используйте кнопки ниже:"
            
            await message.answer(
                admin_text,
                reply_markup=get_user_keyboard(message.from_user.id)
            )
            
            # Отправляем клавиатуру с кнопками управления уведомлениями
            await message.answer(
                "🔔 **Управление уведомлениями:**",
                reply_markup=get_admin_notifications_keyboard()
            )
        finally:
            db.close()
    
    elif message.text == "❓ Помощь":
        help_text = "❓ Помощь\n\n"
        help_text += f"• Для технической поддержки: <a href=\"https://t.me/SeaVPN_support_bot\">@SeaVPN_support_bot</a>\n"
        help_text += "• Время работы поддержки: 24/7\n\n"
        help_text += "📱 Как подключить VPN:\n\n"
        help_text += "<b>Для Android:</b>\n"
        help_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
        help_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
        help_text += "<b>Для iPhone:</b>\n"
        help_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
        help_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
        help_text += "<b>Для Windows:</b>\n"
        help_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">Hiddify</a>\n"
        help_text += "• <a href=\"https://github.com/2dust/v2rayN/releases\">V2rayN</a>\n\n"
        help_text += "<b>Для Mac:</b>\n"
        help_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-MacOS.dmg\">Hiddify</a>\n"
        help_text += "• <a href=\"https://apps.apple.com/ru/app/streisand/id6450534064\">Streisand (Только для M-процессоров)</a>\n"
        help_text += "<b>Инструкция по подключению:</b>\n"
        help_text += "1. Скачайте приложение для вашей платформы\n"
        help_text += "2. Скопируйте подписочную ссылку из раздела '🔑 Мои ключи'\n"
        help_text += "3. Вставьте ссылку в приложение\n"
        help_text += "4. Нажмите 'Подключить'\n\n"
        help_text += "Если у вас есть вопросы, не стесняйтесь обращаться!"
        
        await message.answer(
            help_text,
            parse_mode="HTML",
            reply_markup=get_user_keyboard(message.from_user.id)
        )

# Обработчик выбора тарифа
@dp.message(F.text.in_(["1 месяц - 149₽", "3 месяца - 399₽", "Купить тест (1 день)", "🏢 Корпоративные ключи", "🏢 Корпоративный 1 месяц", "🏢 Корпоративный 3 месяца", "🧪 Тест корпоративный (1 рубль)", "5 пользователей - 1000₽", "10 пользователей - 1800₽", "15 пользователей - 2550₽", "20 пользователей - 3400₽", "5 пользователей - 3000₽", "10 пользователей - 5400₽", "15 пользователей - 7650₽", "20 пользователей - 10200₽"]))
async def tariff_handler(message: Message):
    user = await get_user(message.from_user.id)
    
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    if message.text == "1 месяц - 149₽":
        tariff = "1m"
        price = TARIFFS["1m"]["price"]
        days = TARIFFS["1m"]["days"]
        # Показываем описание тарифа
        tariff_info = f"📋 <b>{TARIFFS['1m']['name']}</b>\n\n"
        tariff_info += TARIFFS['1m']['description']
        tariff_info += f"\n\n💰 <b>Стоимость:</b> {price}₽"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить", callback_data=f"buy_tariff_1m")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tariffs")]
        ])
        
        await message.answer(tariff_info, parse_mode="HTML", reply_markup=keyboard)
        return
        
    elif message.text == "3 месяца - 399₽":
        tariff = "3m"
        price = TARIFFS["3m"]["price"]
        days = TARIFFS["3m"]["days"]
        # Показываем описание тарифа
        tariff_info = f"📋 <b>{TARIFFS['3m']['name']}</b>\n\n"
        tariff_info += TARIFFS['3m']['description']
        tariff_info += f"\n\n💰 <b>Стоимость:</b> {price}₽"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить", callback_data=f"buy_tariff_3m")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tariffs")]
        ])
        
        await message.answer(tariff_info, parse_mode="HTML", reply_markup=keyboard)
        return
        
    elif message.text == "Купить тест (1 день)":
        tariff = "test"
        price = TARIFFS["test"]["price"]
        days = TARIFFS["test"]["days"]
        # Показываем описание тарифа
        tariff_info = f"📋 <b>{TARIFFS['test']['name']}</b>\n\n"
        tariff_info += TARIFFS['test']['description']
        tariff_info += f"\n\n💰 <b>Стоимость:</b> {price}₽"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить", callback_data=f"buy_tariff_test")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tariffs")]
        ])
        
        await message.answer(tariff_info, parse_mode="HTML", reply_markup=keyboard)
        return
        
    elif "Корпоративные ключи" in message.text:
        # Показываем информацию о корпоративных тарифах
        corporate_info = "🏢 <b>Корпоративные ключи</b>\n\n"
        corporate_info += "• Минимум 5 пользователей\n"
        corporate_info += "• Максимум 20 пользователей\n"
        corporate_info += "• Скидки при большем количестве пользователей\n"
        corporate_info += "• Приоритетная техническая поддержка\n\n"
        corporate_info += "Выберите период:"
        
        await message.answer(corporate_info, parse_mode="HTML", reply_markup=get_corporate_keyboard(is_admin=is_admin(message.from_user.id)))
        return
        
    elif "Корпоративный 1 месяц" in message.text:
        # Показываем варианты для корпоративного тарифа 1 месяц
        tariff_info = CORPORATE_TARIFFS["1m"]
        info_text = f"🏢 <b>{tariff_info['name']}</b>\n\n"
        info_text += tariff_info['description']
        info_text += f"\n\n💰 <b>Базовая цена за пользователя:</b> {tariff_info['base_price_per_user']}₽/месяц"
        info_text += f"\n\n📊 <b>Скидки:</b>"
        info_text += f"\n• 5 пользователей: без скидки"
        info_text += f"\n• 10 пользователей: 10% скидка"
        info_text += f"\n• 15 пользователей: 15% скидка"
        info_text += f"\n• 20 пользователей: 15% скидка"
        
        # Создаем клавиатуру с вариантами количества пользователей
        keyboard_buttons = [
            [KeyboardButton(text="5 пользователей - 1000₽")],
            [KeyboardButton(text="10 пользователей - 1800₽")],
            [KeyboardButton(text="15 пользователей - 2550₽")],
            [KeyboardButton(text="20 пользователей - 3400₽")],
            [KeyboardButton(text="Назад")]
        ]
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )
        
        await message.answer(info_text, parse_mode="HTML", reply_markup=keyboard)
        return
        
    elif "Корпоративный 3 месяца" in message.text:
        # Показываем варианты для корпоративного тарифа 3 месяца
        tariff_info = CORPORATE_TARIFFS["3m"]
        info_text = f"🏢 <b>{tariff_info['name']}</b>\n\n"
        info_text += tariff_info['description']
        info_text += f"\n\n💰 <b>Базовая цена за пользователя:</b> {tariff_info['base_price_per_user']}₽/месяц"
        info_text += f"\n\n📊 <b>Скидки:</b>"
        info_text += f"\n• 5 пользователей: без скидки"
        info_text += f"\n• 10 пользователей: 10% скидка"
        info_text += f"\n• 15 пользователей: 15% скидка"
        info_text += f"\n• 20 пользователей: 15% скидка"
        
        # Создаем клавиатуру с вариантами количества пользователей
        keyboard_buttons = [
            [KeyboardButton(text="5 пользователей - 3000₽")],
            [KeyboardButton(text="10 пользователей - 5400₽")],
            [KeyboardButton(text="15 пользователей - 7650₽")],
            [KeyboardButton(text="20 пользователей - 10200₽")],
            [KeyboardButton(text="Назад")]
        ]
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=keyboard_buttons,
            resize_keyboard=True
        )
        
        await message.answer(info_text, parse_mode="HTML", reply_markup=keyboard)
        return
        
    elif message.text == "🧪 Тест корпоративный (1 рубль)":
        # Проверяем, что пользователь админ
        if not is_admin(message.from_user.id):
            await message.answer("❌ Эта функция доступна только администраторам.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
            return
            
        # Создаем тестовый корпоративный платеж за 1 рубль
        await create_test_corporate_payment(message, user)
        return
        
    # Обработка выбора количества пользователей для корпоративных тарифов
    elif "5 пользователей - 1000₽" in message.text:
        await create_corporate_payment(message, user, "1m", 5, 1000)
        return
    elif "10 пользователей - 1800₽" in message.text:
        await create_corporate_payment(message, user, "1m", 10, 1800)
        return
    elif "15 пользователей - 2550₽" in message.text:
        await create_corporate_payment(message, user, "1m", 15, 2550)
        return
    elif "20 пользователей - 3400₽" in message.text:
        await create_corporate_payment(message, user, "1m", 20, 3400)
        return
    elif "5 пользователей - 3000₽" in message.text:
        await create_corporate_payment(message, user, "3m", 5, 3000)
        return
    elif "10 пользователей - 5400₽" in message.text:
        await create_corporate_payment(message, user, "3m", 10, 5400)
        return
    elif "15 пользователей - 7650₽" in message.text:
        await create_corporate_payment(message, user, "3m", 15, 7650)
        return
    elif "20 пользователей - 10200₽" in message.text:
        await create_corporate_payment(message, user, "3m", 20, 10200)
        return
    else:
        await message.answer("Неизвестный тариф. Выберите из списка:", reply_markup=get_tariffs_keyboard(is_admin(message.from_user.id)))
        return
    
    if message.text == "Назад":
        await message.answer("Выберите действие:", reply_markup=get_user_keyboard(message.from_user.id))
        return

async def create_test_subscription(message: Message, user):
    """Создание тестовой подписки"""
    try:
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        
        # Определяем следующий номер подписки
        db = SessionLocal()
        try:
            existing_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id
            ).all()
            next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
        finally:
            db.close()
            
        xui_result = await xui_client.create_user(
            user_email, 
            1,  # 1 день
            f"{user.full_name} (TEST)", 
            str(user.telegram_id), 
            next_subscription_number
        )
        
        if xui_result:
            config = await xui_client.get_user_config(xui_result["email"], next_subscription_number)
            
            if not config:
                await message.answer("❌ Ошибка получения конфигурации. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
                return
                
            # Сохраняем подписку в БД
            db = SessionLocal()
            try:
                expires_at = datetime.utcnow() + timedelta(days=1)
                
                subscription = Subscription(
                    user_id=user.id,
                    plan="test",
                    plan_name="Тестовый (1 день)",
                    status="active",
                    subscription_number=next_subscription_number,
                    key_type="personal",
                    expires_at=expires_at
                )
                db.add(subscription)
                db.commit()
                
                # Формируем сообщение
                apps_text = "\n📱 <b>Рекомендуемые приложения:</b>\n\n"
                apps_text += "<b>Android:</b>\n"
                apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
                apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
                apps_text += "<b>iPhone:</b>\n"
                apps_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
                apps_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
                apps_text += "<b>Windows:</b>\n"
                
                # Отправляем сообщение с конфигурацией
                success_message = f"✅ <b>Тестовая подписка активирована!</b>\n\n"
                success_message += f"📋 <b>Тариф:</b> Тестовый (1 день)\n"
                success_message += f"💰 <b>Стоимость:</b> Бесплатно\n"
                success_message += f"⏰ <b>Действует до:</b> {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                success_message += f"🔗 <b>Конфигурация:</b>\n"
                success_message += f"<code>{config['subscription_url']}</code>\n\n"
                success_message += apps_text
                
                await message.answer(success_message, parse_mode="HTML", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
                
            finally:
                db.close()
        else:
            await message.answer("❌ Ошибка создания пользователя в 3xUI. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
    except Exception as e:
        print(f"Ошибка создания тестовой подписки: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))

async def create_test_corporate_subscription(message: Message, user):
    """Создание тестовой корпоративной подписки"""
    try:
        print(f"DEBUG: Создание тестовой корпоративной подписки для пользователя {user.telegram_id}")
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        print(f"DEBUG: Используемый email: {user_email}")
        
        # Определяем следующий номер подписки
        db = SessionLocal()
        try:
            existing_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id
            ).all()
            next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
        finally:
            db.close()
            
        print(f"DEBUG: Следующий номер подписки: {next_subscription_number}")
        
        # Создаем корпоративную подписку с лимитом 5 пользователей на 1 день
        print(f"DEBUG: Вызываем xui_client.create_user с ip_limit=5")
        xui_result = await xui_client.create_user(
            user_email, 
            1,  # 1 день
            f"{user.full_name} (CORP TEST)", 
            str(user.telegram_id), 
            next_subscription_number,
            ip_limit=5  # Лимит 5 пользователей для корпоративного тарифа
        )
        print(f"DEBUG: Результат xui_client.create_user: {xui_result}")
        
        if xui_result:
            config_url = await xui_client.get_user_config(xui_result["email"], next_subscription_number)
            
            if not config_url:
                await message.answer("❌ Ошибка получения конфигурации. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
                return
                
            # Сохраняем корпоративную подписку в БД
            db = SessionLocal()
            try:
                expires_at = datetime.utcnow() + timedelta(days=1)
                
                subscription = Subscription(
                    user_id=user.id,
                    plan="corporate_test",
                    plan_name="1 день, 5 пользователей",
                    status="active",
                    subscription_number=next_subscription_number,
                    key_type="corporate",
                    expires_at=expires_at
                )
                db.add(subscription)
                db.commit()
                
                # Формируем сообщение
                apps_text = "\n📱 <b>Рекомендуемые приложения:</b>\n\n"
                apps_text += "<b>Android:</b>\n"
                apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
                apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
                apps_text += "<b>iPhone:</b>\n"
                apps_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
                apps_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
                apps_text += "<b>Windows:</b>\n"
                
                # Отправляем сообщение с конфигурацией
                success_message = f"✅ <b>Тестовая корпоративная подписка активирована!</b>\n\n"
                success_message += f"📋 <b>Тариф:</b> Корпоративный тест (1 день)\n"
                success_message += f"👥 <b>Лимит пользователей:</b> 5\n"
                success_message += f"💰 <b>Стоимость:</b> 1₽ (тест)\n"
                success_message += f"⏰ <b>Действует до:</b> {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                success_message += f"🔗 <b>Конфигурация:</b>\n"
                success_message += f"<code>{config_url}</code>\n\n"
                success_message += apps_text
                
                await message.answer(success_message, parse_mode="HTML", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
                
            finally:
                db.close()
        else:
            await message.answer("❌ Ошибка создания пользователя в 3xUI. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
    except Exception as e:
        print(f"Ошибка создания тестовой корпоративной подписки: {e}")
        import traceback
        print(f"Полный traceback: {traceback.format_exc()}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))

async def create_test_corporate_payment(message: Message, user):
    """Создание тестового корпоративного платежа за 1 рубль"""
    try:
        # Создаем платеж в ЮKassa за 1 рубль
        description = "SeaVPN - Корпоративный тест (1 день, 5 пользователей)"
        
        payment_result = yookassa_client.create_payment(
            amount=1,  # 1 рубль
            description=description,
            user_id=user.id,
            subscription_type="corporate_test",
            payment_type="new"
        )
        
        if payment_result["success"]:
            # Сохраняем платеж в БД
            db = SessionLocal()
            try:
                payment = Payment(
                    user_id=user.id,
                    provider="yookassa",
                    invoice_id=payment_result["payment_id"],
                    amount=1,
                    currency="RUB",
                    status="pending",
                    payment_method="yookassa",
                    yookassa_payment_id=payment_result["payment_id"],
                    subscription_type="corporate_test",
                    description=description
                )
                db.add(payment)
                db.commit()
                
                # Создаем клавиатуру для оплаты
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить 1₽", url=payment_result["confirmation_url"])],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment_result['payment_id']}")]
                ])
                
                payment_message = f"💳 <b>Тестовый корпоративный платеж</b>\n\n"
                payment_message += f"📋 <b>Тариф:</b> Корпоративный тест (1 день, 5 пользователей)\n"
                payment_message += f"👥 <b>Лимит пользователей:</b> 5\n"
                payment_message += f"💰 <b>Сумма:</b> 1₽ (тест)\n"
                payment_message += f"⏰ <b>Срок:</b> 1 день\n\n"
                payment_message += f"🔗 <b>Ссылка для оплаты:</b>\n"
                payment_message += f"Нажмите кнопку 'Оплатить 1₽' ниже\n\n"
                payment_message += f"✅ <b>После оплаты корпоративная подписка активируется автоматически</b>"
                
                await message.answer(payment_message, parse_mode="HTML", reply_markup=keyboard)
                
            finally:
                db.close()
        else:
            await message.answer(f"❌ Ошибка создания платежа: {payment_result.get('error', 'Неизвестная ошибка')}", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
            
    except Exception as e:
        print(f"Ошибка создания тестового корпоративного платежа: {e}")
        import traceback
        print(f"Полный traceback: {traceback.format_exc()}")
        await message.answer("❌ Произошла ошибка при создании платежа. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))

async def create_payment_for_tariff(message: Message, user, tariff: str, price: int, days: int):
    """Создание платежа для тарифа"""
    try:
        # Создаем платеж в ЮKassa
        description = f"SeaVPN - {TARIFFS[tariff]['name']}"
        
        payment_result = yookassa_client.create_payment(
            amount=price,
            description=description,
            user_id=user.id,
            subscription_type=tariff,
            payment_type="new"
        )
        
        if payment_result["success"]:
            # Сохраняем платеж в БД
            db = SessionLocal()
            try:
                payment = Payment(
                    user_id=user.id,
                    provider="yookassa",
                    invoice_id=payment_result["payment_id"],
                    amount=price,
                    currency="RUB",
                    status="pending",
                    payment_method="yookassa",
                    yookassa_payment_id=payment_result["payment_id"],
                    subscription_type=tariff,
                    description=description
                )
                db.add(payment)
                db.commit()
                
                # Создаем клавиатуру для оплаты
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить", url=payment_result["confirmation_url"])],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment_result['payment_id']}")]
                ])
                
                payment_message = f"💳 <b>Оплата подписки</b>\n\n"
                payment_message += f"📋 <b>Тариф:</b> {TARIFFS[tariff]['name']}\n"
                payment_message += f"💰 <b>Сумма:</b> {price}₽\n"
                payment_message += f"⏰ <b>Срок:</b> {days} дней\n\n"
                payment_message += f"🔗 <b>Ссылка для оплаты:</b>\n"
                payment_message += f"Нажмите кнопку 'Оплатить' ниже\n\n"
                payment_message += f"✅ <b>После оплаты подписка активируется автоматически</b>"
                
                await message.answer(payment_message, parse_mode="HTML", reply_markup=keyboard)
                
            finally:
                db.close()
        else:
            await message.answer(f"❌ Ошибка создания платежа: {payment_result.get('error', 'Неизвестная ошибка')}", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
            
    except Exception as e:
        print(f"Ошибка создания платежа: {e}")
        await message.answer("❌ Произошла ошибка при создании платежа. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))



# Обработчик синхронизации с 3xUI
@dp.message(F.text == "🔄 Синхронизировать с 3xUI")
async def sync_handler(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    await message.answer("🔄 Синхронизация с 3xUI...")
    
    try:
        # Получаем все активные подписки пользователя
        db = SessionLocal()
        try:
            active_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.status == "active",
                Subscription.expires_at > datetime.utcnow()
            ).order_by(Subscription.subscription_number).all()
        finally:
            db.close()
        
        if not active_subscriptions:
            await message.answer(
                "У вас нет активных ключей.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Собираем актуальные конфигурации по уникальным email
        message_text = "✅ Синхронизация завершена!\n\n"
        any_found = False
        for subscription in active_subscriptions:
            unique_email = f"SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number}"
            config = await xui_client.get_user_config(unique_email, subscription.subscription_number)
            if config:
                any_found = True
                days_left = (subscription.expires_at - datetime.utcnow()).days
                message_text += f"**Подписка #{subscription.subscription_number}**\n"
                message_text += f"Тариф: {subscription.plan_name}\n"
                message_text += f"Действует до: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
                if days_left <= 0:
                    message_text += "⚠️ Подписка истекла!\n"
                elif days_left <= 3:
                    message_text += f"⚠️ Подписка истекает через {days_left} дней!\n"
                elif days_left <= 7:
                    message_text += f"📅 Подписка истекает через {days_left} дней\n"
                else:
                    message_text += "✅ Подписка активна\n"
                message_text += f"Конфигурация:\n`{config}`\n\n"
        
        if any_found:
            await message.answer(
                message_text,
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await message.answer(
                "❌ Конфигурации не найдены. Обратитесь в поддержку.",
                reply_markup=get_main_menu_keyboard()
            )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при синхронизации: {e}",
            reply_markup=get_main_menu_keyboard()
        )

# Обработчик обмена монет на подписку
@dp.message(F.text.in_(["🪙 Купить 1 месяц за 150 монет", "🪙 Купить 3 месяца за 450 монет"]))
async def exchange_bonus_handler(message: Message):
    print(f"DEBUG: Запущен обработчик обмена монет на подписку с текстом: {message.text}")
    user = await get_user(message.from_user.id)
    
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    # Определяем тариф и стоимость
    print(f"DEBUG: Определяем тариф для текста: '{message.text}'")
    if message.text == "🪙 Купить 1 месяц за 150 монет":
        required_coins = BONUS_TO_SUBSCRIPTION
        months = 1
        tariff_name = "1 месяц (за бонусы)"
        print(f"DEBUG: Выбран тариф: 1 месяц за {required_coins} монет")
    elif message.text == "🪙 Купить 3 месяца за 450 монет":
        required_coins = BONUS_TO_SUBSCRIPTION * 3
        months = 3
        tariff_name = "3 месяца (за бонусы)"
        print(f"DEBUG: Выбран тариф: 3 месяца за {required_coins} монет")
    else:
        print(f"DEBUG: Неизвестный тариф: '{message.text}'")
        await message.answer("Неизвестный тариф", reply_markup=get_main_menu_keyboard())
        return
    
    # Проверяем, достаточно ли монет
    if user.bonus_coins < required_coins:
        await message.answer(
            f"❌ Недостаточно монет для обмена.\n\n"
            f"Необходимо: {required_coins} монет\n"
            f"У вас: {user.bonus_coins} монет\n\n"
            f"Продолжайте приглашать друзей для получения бонусов!",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Создаем пользователя в 3xUI
    try:
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        days = months * 30
        
        # Определяем следующий номер подписки для пользователя
        db = SessionLocal()
        try:
            existing_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id
            ).all()
            next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
        finally:
            db.close()
            
        xui_result = await xui_client.create_user(
            user_email, 
            days, 
            f"{user.full_name} (BONUS)", 
            str(user.telegram_id), 
            next_subscription_number
        )
        
        if xui_result:
            # Проверяем, был ли создан новый пользователь или используется существующий
            if xui_result.get("existing"):
                # Используем существующую конфигурацию
                config = await xui_client.get_user_config(xui_result["email"], next_subscription_number)
            else:
                # Получаем конфигурацию для нового пользователя
                config = await xui_client.get_user_config(xui_result["email"], next_subscription_number)
            
            if config:
                # Сохраняем подписку в БД
                db = SessionLocal()
                try:
                    
                    subscription = Subscription(
                        user_id=user.id,
                        plan="bonus",
                        plan_name=tariff_name,
                        status="active",
                        subscription_number=next_subscription_number,
                        expires_at=datetime.utcnow() + timedelta(days=days)
                    )
                    db.add(subscription)
                    
                    # Списываем монеты
                    user.bonus_coins -= required_coins
                    
                    # Обновляем пользователя в базе данных
                    db.merge(user)
                    db.commit()
                    
                    # Обновляем объект user в памяти
                    user = db.query(User).filter(User.id == user.id).first()
                    
                    # Формируем ссылки на приложения
                    apps_text = "\n📱 <b>Рекомендуемые приложения:</b>\n\n"
                    apps_text += "<b>Android:</b>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
                    apps_text += "<b>iPhone:</b>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
                    apps_text += "<b>Windows:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://github.com/2dust/v2rayN/releases\">V2rayN</a>\n\n"
                    apps_text += "<b>Mac:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-MacOS.dmg\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/ru/app/streisand/id6450534064\">Streisand (Только для M-процессоров)</a>\n"
                    
                    await message.answer(
                        f"✅ Бонусная подписка активирована!\n\n"
                        f"Тариф: {tariff_name}\n"
                        f"Списано монет: {required_coins} 🪙\n"
                        f"Остаток монет: {user.bonus_coins} 🪙\n"
                        f"Действует до: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
                        f"Ваша конфигурация:\n<code>{config}</code>\n\n"
                        f"Скопируйте эту ссылку в ваш VPN клиент."
                        f"{apps_text}",
                        parse_mode="HTML",
                        reply_markup=get_user_keyboard(message.from_user.id)
                    )
                    
                    # Отправляем уведомление администраторам о бонусной подписке
                    settings = get_admin_settings()
                    if settings.notifications_enabled and settings.subscription_notifications:
                        notification_text = (
                            f"🎁 **Бонусная подписка активирована!**\n\n"
                            f"👤 Пользователь: {user.full_name}\n"
                            f"🆔 Telegram ID: {user.telegram_id}\n"
                            f"📧 Email: {user.email or 'Не указан'}\n"
                            f"📦 Тариф: {tariff_name}\n"
                            f"🪙 Списано монет: {required_coins} 🪙\n"
                            f"💰 Стоимость: {required_coins} монет\n"
                            f"📅 Действует до: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
                            f"🕐 Время активации: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                        )
                        await send_admin_notification(notification_text)
                finally:
                    db.close()
            else:
                await message.answer(
                    "Ошибка при получении конфигурации. Обратитесь в поддержку.",
                    reply_markup=get_main_menu_keyboard()
                )
        else:
            await message.answer(
                "Ошибка при создании пользователя в системе. Обратитесь в поддержку.",
                reply_markup=get_main_menu_keyboard()
            )
    except Exception as e:
        print(f"Ошибка при обмене бонусов: {e}")
        await message.answer(
            "Произошла ошибка при обмене бонусов. Попробуйте позже или обратитесь в поддержку.",
            reply_markup=get_main_menu_keyboard()
        )

# Обработчик кнопки "Назад"
@dp.message(F.text == "Назад")
async def back_handler(message: Message):
    user = await get_user(message.from_user.id)
    
    if user:
        await message.answer(
            "Выберите действие:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer(
            "Пожалуйста, сначала зарегистрируйтесь. Нажмите /start"
        )

# Обработчик неизвестных сообщений
@dp.message()
async def unknown_handler(message: Message):
    user = await get_user(message.from_user.id)
    
    if user:
        await message.answer(
            "Используйте кнопки меню для навигации:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer(
            "Пожалуйста, сначала зарегистрируйтесь. Нажмите /start"
        )

# Обработчики callback кнопок для уведомлений
@dp.callback_query(lambda c: c.data.startswith('notifications_'))
async def notifications_callback_handler(callback: CallbackQuery):
    """Обработчик кнопок управления уведомлениями"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет доступа к этой функции.")
        return
    
    action = callback.data.split('_')[1]
    
    if action == "on":
        settings = update_admin_settings(notifications_enabled=True)
        await callback.answer("✅ Уведомления включены!")
        await callback.message.edit_text(
            "🔔 **Уведомления включены!**\n\n"
            "Теперь вы будете получать уведомления о:\n"
            "• Новых регистрациях пользователей\n"
            "• Покупках подписок\n"
            "• Активации бонусных подписок",
            reply_markup=get_admin_notifications_keyboard()
        )
    
    elif action == "off":
        settings = update_admin_settings(notifications_enabled=False)
        await callback.answer("🔕 Уведомления отключены!")
        await callback.message.edit_text(
            "🔕 **Уведомления отключены!**\n\n"
            "Вы больше не будете получать уведомления о новых пользователях и покупках.",
            reply_markup=get_admin_notifications_keyboard()
        )
    
    elif action == "status":
        settings = get_admin_settings()
        status_text = "🔔 **Статус уведомлений:**\n\n"
        
        if settings.notifications_enabled:
            status_text += "✅ Уведомления включены\n"
            status_text += f"👥 Новые пользователи: {'✅' if settings.new_user_notifications else '❌'}\n"
            status_text += f"💳 Покупки подписок: {'✅' if settings.subscription_notifications else '❌'}\n"
        else:
            status_text += "❌ Уведомления отключены\n"
        
        status_text += f"\n🕐 Последнее обновление: {settings.created_at.strftime('%d.%m.%Y %H:%M') if settings.created_at else 'Неизвестно'}"
        
        await callback.answer("📊 Статус загружен!")
        await callback.message.edit_text(
            status_text,
            reply_markup=get_admin_notifications_keyboard()
        )
    
    elif action == "back":
        await callback.message.delete()

# Обработчики команд управления уведомлениями
@dp.message(F.text == "/notifications_on")
async def notifications_on_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    settings = update_admin_settings(notifications_enabled=True)
    await message.answer(
        "✅ Уведомления включены!\n\n"
        "Теперь вы будете получать уведомления о:\n"
        "• Новых регистрациях пользователей\n"
        "• Покупках подписок\n"
        "• Активации бонусных подписок",
        reply_markup=get_user_keyboard(message.from_user.id)
    )

@dp.message(F.text == "/notifications_off")
async def notifications_off_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    settings = update_admin_settings(notifications_enabled=False)
    await message.answer(
        "🔕 Уведомления отключены!\n\n"
        "Вы больше не будете получать уведомления о новых пользователях и покупках.",
        reply_markup=get_user_keyboard(message.from_user.id)
    )

@dp.message(F.text == "/notifications_status")
async def notifications_status_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к этой команде.")
        return
    
    settings = get_admin_settings()
    status_text = "🔔 **Статус уведомлений:**\n\n"
    
    if settings.notifications_enabled:
        status_text += "✅ Уведомления включены\n"
        status_text += f"👥 Новые пользователи: {'✅' if settings.new_user_notifications else '❌'}\n"
        status_text += f"💳 Покупки подписок: {'✅' if settings.subscription_notifications else '❌'}\n"
    else:
        status_text += "❌ Уведомления отключены\n"
    
    status_text += f"\n🕐 Последнее обновление: {settings.created_at.strftime('%d.%m.%Y %H:%M') if settings.created_at else 'Неизвестно'}"
    
    await message.answer(
        status_text,
        parse_mode="Markdown",
        reply_markup=get_user_keyboard(message.from_user.id)
    )



# Обработчики кнопок продления подписки
@dp.callback_query(lambda c: c.data.startswith('extend_'))
async def extend_subscription_handler(callback: CallbackQuery):
    """Обработчик продления подписки"""
    try:
        # Парсим данные из callback
        parts = callback.data.split('_')
        if len(parts) < 4:
            await callback.answer("Ошибка: неверный формат данных")
            return
        
        # Проверяем тип продления (обычное или за бонусы)
        if parts[1] == "bonus":
            is_bonus = True
            subscription_id = int(parts[2])
            tariff = parts[3]  # 1m или 3m
        elif parts[1] == "paid":
            is_bonus = False
            subscription_id = int(parts[2])
            tariff = parts[3]  # 1m или 3m
        else:
            await callback.answer("Ошибка: неверный тип продления")
            return
        
        user = await get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        # Получаем подписку
        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
            if not subscription or subscription.user_id != user.id:
                await callback.answer("Подписка не найдена")
                return
            
            # Определяем параметры продления
            if tariff == "test":
                days = 1
                if is_bonus:
                    required_coins = 5  # Минимальная стоимость для бонусного продления
                    tariff_name = "Тест (1 день) (бонусная)"
                else:
                    price = TARIFFS['test']['price']
                    tariff_name = "Тест (1 день)"
            elif tariff == "1m":
                days = 30
                if is_bonus:
                    required_coins = 150
                    tariff_name = "1 месяц (бонусная)"
                else:
                    price = TARIFFS['1m']['price']
                    tariff_name = "1 месяц"
            elif tariff == "3m":
                days = 90
                if is_bonus:
                    required_coins = 450
                    tariff_name = "3 месяца (бонусная)"
                else:
                    price = TARIFFS['3m']['price']
                    tariff_name = "3 месяца"
            else:
                await callback.answer("Неизвестный тариф")
                return
            
            # Проверяем бонусы если это продление за бонусы
            if is_bonus:
                if user.bonus_coins < required_coins:
                    await callback.answer(f"Недостаточно монет! Нужно: {required_coins}, у вас: {user.bonus_coins}")
                    return
                
                # Продлеваем подписку за бонусы
                await extend_subscription_with_bonus(callback, user, subscription, tariff, days, required_coins, tariff_name)
            else:
                # Создаем платеж для платного продления
                await create_payment_for_extension(callback, user, subscription, tariff, price, days, tariff_name)
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка при продлении подписки: {e}")
        await callback.answer("Произошла ошибка при продлении")

async def extend_subscription_with_bonus(callback: CallbackQuery, user, subscription, tariff: str, days: int, required_coins: int, tariff_name: str):
    """Продление подписки за бонусы"""
    try:
        db = SessionLocal()
        try:
            # Продлеваем подписку в 3xUI
            user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
            unique_email = f"SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number}"
            
            # Если подписка истекла, создаем нового пользователя
            if subscription.status == "expired":
                xui_result = await xui_client.create_user(
                    user_email, 
                    days, 
                    f"{user.full_name} (EXTENDED)", 
                    str(user.telegram_id),
                    subscription.subscription_number
                )
            else:
                # Если подписка еще активна, продлеваем существующего пользователя
                xui_result = await xui_client.extend_user(
                    unique_email,
                    days
                )
            
            if xui_result:
                # Получаем новую конфигурацию
                config = await xui_client.get_user_config(xui_result["email"], subscription.subscription_number)
                
                if config:
                    # Обновляем подписку в БД
                    if subscription.status == "expired":
                        subscription.expires_at = datetime.utcnow() + timedelta(days=days)
                    else:
                        subscription.expires_at = subscription.expires_at + timedelta(days=days)
                    
                    # Обновляем поля продлений
                    subscription.extensions_count += 1
                    subscription.last_extension_date = datetime.utcnow()
                    subscription.total_days_added += days
                    subscription.status = "active"
                    
                    # Списываем монеты
                    user.bonus_coins -= required_coins
                    db.merge(user)
                    db.commit()
                    
                    # Формируем ссылки на приложения
                    apps_text = "\n📱 <b>Рекомендуемые приложения:</b>\n\n"
                    apps_text += "<b>Android:</b>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
                    apps_text += "<b>iPhone:</b>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
                    apps_text += "<b>Windows:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://github.com/2dust/v2rayN/releases\">V2rayN</a>\n\n"
                    apps_text += "<b>Mac:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-MacOS.dmg\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/ru/app/streisand/id6450534064\">Streisand (Только для M-процессоров)</a>\n"
                    
                    await callback.message.edit_text(
                        f"✅ Подписка успешно продлена за бонусы!\n\n"
                        f"Тариф: {tariff_name}\n"
                        f"Списано монет: {required_coins} 🪙\n"
                        f"Остаток монет: {user.bonus_coins} 🪙\n"
                        f"Новая дата окончания: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"Ваша конфигурация:\n<code>{config}</code>\n\n"
                        f"Скопируйте эту ссылку в ваш VPN клиент."
                        f"{apps_text}",
                        parse_mode="HTML"
                    )
                    
                    await callback.answer("Подписка продлена успешно!")
                else:
                    await callback.answer("Ошибка при получении конфигурации")
            else:
                await callback.answer("Ошибка при продлении подписки")
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка при продлении подписки за бонусы: {e}")
        await callback.answer("Произошла ошибка при продлении")

async def create_payment_for_extension(callback: CallbackQuery, user, subscription, tariff: str, price: int, days: int, tariff_name: str):
    """Создание платежа для продления подписки"""
    try:
        # Создаем платеж в ЮKassa
        description = f"SeaVPN - Продление {tariff_name}"
        
        payment_result = yookassa_client.create_payment(
            amount=price,
            description=description,
            user_id=user.id,
            subscription_type=tariff,
            payment_type="extension",
            subscription_id=subscription.id
        )
        
        if payment_result["success"]:
            # Сохраняем платеж в БД с метаданными для продления
            db = SessionLocal()
            try:
                payment = Payment(
                    user_id=user.id,
                    provider="yookassa",
                    invoice_id=payment_result["payment_id"],
                    amount=price,
                    currency="RUB",
                    status="pending",
                    payment_method="yookassa",
                    yookassa_payment_id=payment_result["payment_id"],
                    subscription_type=tariff,
                    description=description,
                    payment_type="extension",  # Указываем тип платежа
                    payment_metadata=json.dumps({"subscription_id": subscription.id})  # Сохраняем ID подписки для продления
                )
                db.add(payment)
                db.commit()
                
                # Создаем клавиатуру для оплаты
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить", url=payment_result["confirmation_url"])],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment_result['payment_id']}")]
                ])
                
                payment_message = f"💳 <b>Оплата продления подписки</b>\n\n"
                payment_message += f"📋 <b>Тариф:</b> {tariff_name}\n"
                payment_message += f"💰 <b>Сумма:</b> {price}₽\n"
                payment_message += f"⏰ <b>Дополнительно дней:</b> {days}\n"
                payment_message += f"📅 <b>Текущая дата окончания:</b> {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                payment_message += f"🔗 <b>Ссылка для оплаты:</b>\n"
                payment_message += f"Нажмите кнопку 'Оплатить' ниже\n\n"
                payment_message += f"✅ <b>После оплаты подписка продлится автоматически</b>"
                
                await callback.message.edit_text(payment_message, parse_mode="HTML", reply_markup=keyboard)
                
            finally:
                db.close()
        else:
            await callback.answer(f"❌ Ошибка создания платежа: {payment_result.get('error', 'Неизвестная ошибка')}")
            
    except Exception as e:
        print(f"Ошибка создания платежа для продления: {e}")
        await callback.answer("❌ Произошла ошибка при создании платежа. Попробуйте позже.")

@dp.callback_query(lambda c: c.data.startswith('check_payment_'))
async def check_payment_handler(callback: CallbackQuery):
    """Обработчик проверки платежа"""
    try:
        payment_id = callback.data.split('_')[2]
        
        # Проверяем статус платежа в ЮKassa
        payment_status = yookassa_client.check_payment_status(payment_id)
        
        if not payment_status["success"]:
            await callback.answer("❌ Ошибка проверки платежа", show_alert=True)
            return
        
        if payment_status["paid"]:
            # Платеж оплачен - создаем подписку
            await process_paid_payment(callback, payment_id, payment_status)
        else:
            await callback.answer("⏳ Платеж еще не оплачен. Попробуйте позже.", show_alert=True)
            
    except Exception as e:
        print(f"Ошибка проверки платежа: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('buy_tariff_'))
async def buy_tariff_handler(callback: CallbackQuery):
    """Обработчик покупки тарифа"""
    try:
        user = await get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пожалуйста, сначала зарегистрируйтесь", show_alert=True)
            return
        
        tariff = callback.data.split('_')[2]  # 1m, 3m, test
        
        if tariff == "test":
            price = TARIFFS["test"]["price"]
            days = TARIFFS["test"]["days"]
        elif tariff == "1m":
            price = TARIFFS["1m"]["price"]
            days = TARIFFS["1m"]["days"]
        elif tariff == "3m":
            price = TARIFFS["3m"]["price"]
            days = TARIFFS["3m"]["days"]
        else:
            await callback.answer("Неизвестный тариф", show_alert=True)
            return
        
        # Создаем платеж
        await create_payment_for_tariff(callback.message, user, tariff, price, days)
        
    except Exception as e:
        print(f"Ошибка покупки тарифа: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data in ['corporate_1m', 'corporate_3m'])
async def corporate_tariff_handler(callback: CallbackQuery):
    """Обработчик выбора корпоративного тарифа"""
    try:
        tariff_type = callback.data.split('_')[1]  # 1m или 3m
        
        if tariff_type not in ["1m", "3m"]:
            await callback.answer("Неизвестный тип тарифа", show_alert=True)
            return
        
        tariff_info = CORPORATE_TARIFFS[tariff_type]
        
        # Показываем информацию о корпоративном тарифе
        info_text = f"🏢 <b>{tariff_info['name']}</b>\n\n"
        info_text += tariff_info['description']
        info_text += f"\n\n💰 <b>Базовая цена за пользователя:</b> {tariff_info['base_price_per_user']}₽/месяц"
        info_text += f"\n\n📊 <b>Скидки:</b>"
        info_text += f"\n• 5 пользователей: без скидки"
        info_text += f"\n• 10 пользователей: 10% скидка"
        info_text += f"\n• 15 пользователей: 15% скидка"
        info_text += f"\n• 20 пользователей: 15% скидка"
        
    except Exception as e:
        print(f"Ошибка корпоративного тарифа: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)


@dp.callback_query(lambda c: c.data.startswith('buy_corporate_'))
async def buy_corporate_handler(callback: CallbackQuery):
    """Обработчик покупки корпоративного тарифа"""
    try:
        user = await get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пожалуйста, сначала зарегистрируйтесь", show_alert=True)
            return
        
        # Парсим данные из callback_data: buy_corporate_1m_10_1800
        parts = callback.data.split('_')
        tariff_type = parts[2]  # 1m или 3m
        users_count = int(parts[3])  # количество пользователей
        total_price = int(parts[4])  # общая стоимость
        
        # Создаем платеж для корпоративного тарифа
        tariff_info = CORPORATE_TARIFFS[tariff_type]
        description = f"SeaVPN - {tariff_info['name']} ({users_count} пользователей)"
        
        payment_result = yookassa_client.create_payment(
            amount=total_price,
            description=description,
            user_id=user.id,
            subscription_type=f"corporate_{tariff_type}",
            payment_type="new"
        )
        
        if payment_result["success"]:
            # Сохраняем платеж в БД
            db = SessionLocal()
            try:
                payment = Payment(
                    user_id=user.id,
                    provider="yookassa",
                    invoice_id=payment_result["payment_id"],
                    amount=total_price,
                    currency="RUB",
                    status="pending",
                    payment_method="yookassa",
                    yookassa_payment_id=payment_result["payment_id"],
                    subscription_type=f"corporate_{tariff_type}",
                    description=description,
                    payment_metadata=json.dumps({
                        "users_count": users_count,
                        "tariff_type": tariff_type,
                        "key_type": "corporate"
                    })
                )
                db.add(payment)
                db.commit()
                
                # Создаем клавиатуру для оплаты
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить", url=payment_result["confirmation_url"])],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment_result['payment_id']}")]
                ])
                
                payment_message = f"💳 <b>Оплата корпоративного тарифа</b>\n\n"
                payment_message += f"📋 <b>Тариф:</b> {tariff_info['name']}\n"
                payment_message += f"👥 <b>Пользователей:</b> {users_count}\n"
                payment_message += f"💰 <b>Сумма:</b> {total_price}₽\n"
                payment_message += f"⏰ <b>Срок:</b> {tariff_info['days']} дней\n\n"
                payment_message += f"🔗 <b>Ссылка для оплаты:</b>\n"
                payment_message += f"Нажмите кнопку 'Оплатить' ниже\n\n"
                payment_message += f"✅ <b>После оплаты подписка активируется автоматически</b>"
                
                await callback.message.edit_text(payment_message, parse_mode="HTML", reply_markup=keyboard)
                
            finally:
                db.close()
        else:
            await callback.answer(f"❌ Ошибка создания платежа: {payment_result.get('error', 'Неизвестная ошибка')}", show_alert=True)
            
    except Exception as e:
        print(f"Ошибка покупки корпоративного тарифа: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('cancel_payment_'))
async def cancel_payment_handler(callback: CallbackQuery):
    """Обработчик отмены платежа"""
    try:
        payment_id = callback.data.split('_')[2]
        
        # Обновляем статус платежа в БД
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(Payment.yookassa_payment_id == payment_id).first()
            if payment:
                payment.status = "canceled"
                db.commit()
                await callback.answer("✅ Платеж отменен", show_alert=True)
            else:
                await callback.answer("❌ Платеж не найден", show_alert=True)
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка отмены платежа: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

async def process_paid_payment(callback: CallbackQuery, payment_id: str, payment_status: dict):
    """Обработка оплаченного платежа"""
    try:
        db = SessionLocal()
        try:
            # Получаем платеж из БД
            payment = db.query(Payment).filter(Payment.yookassa_payment_id == payment_id).first()
            if not payment:
                await callback.answer("❌ Платеж не найден в БД", show_alert=True)
                return
            
            # Проверяем, что платеж еще не обработан
            if payment.status == "completed":
                await callback.answer("✅ Платеж уже обработан", show_alert=True)
                return
            
            # Получаем пользователя
            user = db.query(User).filter(User.id == payment.user_id).first()
            if not user:
                await callback.answer("❌ Пользователь не найден", show_alert=True)
                return
            
            # Определяем параметры подписки
            tariff = payment.subscription_type
            key_type = "personal"  # по умолчанию личный ключ
            
            if tariff == "test":
                days = TARIFFS["test"]["days"]
                tariff_name = TARIFFS["test"]["name"]
            elif tariff == "1m":
                days = TARIFFS["1m"]["days"]
                tariff_name = TARIFFS["1m"]["name"]
            elif tariff == "3m":
                days = TARIFFS["3m"]["days"]
                tariff_name = TARIFFS["3m"]["name"]
            elif tariff == "corporate_test":
                # Тестовый корпоративный тариф
                days = 1
                tariff_name = "1 день, 5 пользователей"
                key_type = "corporate"
                users_count = 5
            elif tariff.startswith("corporate_"):
                # Корпоративный тариф
                corporate_tariff_type = tariff.split("_")[1]  # 1m или 3m
                days = CORPORATE_TARIFFS[corporate_tariff_type]["days"]
                tariff_name = CORPORATE_TARIFFS[corporate_tariff_type]["name"]
                key_type = "corporate"
                
                # Получаем количество пользователей из метаданных
                if payment.payment_metadata:
                    try:
                        metadata = json.loads(payment.payment_metadata)
                        users_count = metadata.get("users_count", 5)
                        tariff_name += f" ({users_count} пользователей)"
                    except:
                        users_count = 5
                        tariff_name += " (5 пользователей)"
                else:
                    users_count = 5
                    tariff_name += " (5 пользователей)"
            else:
                await callback.answer("❌ Неизвестный тариф", show_alert=True)
                return
            
            # Создаем подписку в 3xUI
            user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
            
            # Определяем следующий номер подписки
            existing_subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
            next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
            
            # Определяем лимит IP для корпоративных тарифов
            ip_limit = 3  # по умолчанию для личных тарифов
            if key_type == "corporate":
                ip_limit = users_count  # для корпоративных тарифов лимит = количество пользователей
            
            xui_result = await xui_client.create_user(
                user_email, 
                days, 
                f"{user.full_name} (PAID)", 
                str(user.telegram_id), 
                next_subscription_number,
                ip_limit=ip_limit
            )
            
            if xui_result:
                config = await xui_client.get_user_config(xui_result["email"], next_subscription_number)
                
                if config:
                    # Создаем подписку в БД
                    expires_at = datetime.utcnow() + timedelta(days=days)
                    
                    subscription = Subscription(
                        user_id=user.id,
                        plan=tariff,
                        plan_name=tariff_name,
                        status="active",
                        subscription_number=next_subscription_number,
                        key_type=key_type,
                        expires_at=expires_at
                    )
                    db.add(subscription)
                    
                    # Обновляем статус платежа
                    payment.status = "completed"
                    payment.completed_at = datetime.utcnow()
                    
                    db.commit()
                    
                    # Создаем чек
                    if user.email:
                        receipt_result = yookassa_client.create_receipt(
                            payment_id, 
                            user.email, 
                            payment.amount, 
                            payment.description
                        )
                        if receipt_result["success"]:
                            payment.receipt_sent = True
                            db.commit()
                    
                    # Формируем сообщение с конфигурацией
                    apps_text = "\n📱 <b>Рекомендуемые приложения:</b>\n\n"
                    apps_text += "<b>Android:</b>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
                    apps_text += "<b>iPhone:</b>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
                    apps_text += "<b>Windows:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://github.com/2dust/v2rayN/releases\">V2rayN</a>\n\n"
                    apps_text += "<b>Mac:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases/download/v2.5.7/Hiddify-MacOS.dmg\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://github.com/yichengchen/clashX/releases\">ClashX</a>\n\n"
                    
                    success_message = f"✅ <b>Оплата прошла успешно!</b>\n\n"
                    success_message += f"📋 <b>Тариф:</b> {tariff_name}\n"
                    success_message += f"💰 <b>Сумма:</b> {payment.amount}₽\n"
                    success_message += f"⏰ <b>Действует до:</b> {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                    success_message += f"🔗 <b>Конфигурация:</b>\n"
                    if isinstance(config, dict) and 'subscription_url' in config:
                        success_message += f"<code>{config['subscription_url']}</code>\n\n"
                    else:
                        success_message += f"<code>{config}</code>\n\n"
                    success_message += apps_text
                    
                    # Отправляем сообщение пользователю
                    await callback.message.edit_text(success_message, parse_mode="HTML")
                    await callback.answer("✅ Подписка активирована!", show_alert=True)
                    
                    # Начисляем реферальный бонус только при первой покупке
                    if user.referred_by and not user.has_made_first_purchase:
                        referrer = db.query(User).filter(User.id == user.referred_by).first()
                        if referrer:
                            referrer.bonus_coins += REFERRAL_BONUS
                            user.has_made_first_purchase = True
                            db.merge(referrer)
                            db.merge(user)
                            db.commit()
                            
                            # Отправляем уведомление о реферальном бонусе
                            if notification_manager:
                                await notification_manager.notify_referral_bonus(referrer.telegram_id, user.full_name)
                    
                else:
                    await callback.answer("❌ Ошибка получения конфигурации", show_alert=True)
            else:
                await callback.answer("❌ Ошибка создания подписки", show_alert=True)
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка обработки оплаченного платежа: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

async def create_corporate_payment(message: Message, user, tariff_type: str, users_count: int, total_price: int):
    """Создание платежа для корпоративного тарифа"""
    try:
        # Создаем платеж для корпоративного тарифа
        tariff_info = CORPORATE_TARIFFS[tariff_type]
        description = f"SeaVPN - {tariff_info['name']} ({users_count} пользователей)"
        
        payment_result = yookassa_client.create_payment(
            amount=total_price,
            description=description,
            user_id=user.id,
            subscription_type=f"corporate_{tariff_type}",
            payment_type="new"
        )
        
        if payment_result["success"]:
            # Сохраняем платеж в БД
            db = SessionLocal()
            try:
                payment = Payment(
                    user_id=user.id,
                    provider="yookassa",
                    invoice_id=payment_result["payment_id"],
                    amount=total_price,
                    currency="RUB",
                    status="pending",
                    payment_method="yookassa",
                    yookassa_payment_id=payment_result["payment_id"],
                    subscription_type=f"corporate_{tariff_type}",
                    description=description,
                    payment_metadata=json.dumps({
                        "users_count": users_count,
                        "tariff_type": tariff_type,
                        "key_type": "corporate"
                    })
                )
                db.add(payment)
                db.commit()
                
                # Создаем клавиатуру для оплаты
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить", url=payment_result["confirmation_url"])],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_payment_{payment_result['payment_id']}")]
                ])
                
                payment_message = f"💳 <b>Оплата корпоративного тарифа</b>\n\n"
                payment_message += f"📋 <b>Тариф:</b> {tariff_info['name']}\n"
                payment_message += f"👥 <b>Пользователей:</b> {users_count}\n"
                payment_message += f"💰 <b>Сумма:</b> {total_price}₽\n"
                payment_message += f"⏰ <b>Срок:</b> {tariff_info['days']} дней\n\n"
                payment_message += f"🔗 <b>Ссылка для оплаты:</b>\n"
                payment_message += f"Нажмите кнопку 'Оплатить' ниже\n\n"
                payment_message += f"✅ <b>После оплаты подписка активируется автоматически</b>"
                
                await message.answer(payment_message, parse_mode="HTML", reply_markup=keyboard)
                
            finally:
                db.close()
        else:
            await message.answer(f"❌ Ошибка создания платежа: {payment_result.get('error', 'Неизвестная ошибка')}", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))
            
    except Exception as e:
        print(f"Ошибка создания корпоративного платежа: {e}")
        await message.answer("❌ Произошла ошибка при создании платежа. Попробуйте позже.", reply_markup=get_main_menu_keyboard(is_admin(message.from_user.id)))

# ===== Обработчики для массовых уведомлений =====

@dp.message(NotificationStates.waiting_for_title)
async def notification_title_handler(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отправка уведомления отменена.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return
    
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("Заголовок должен содержать минимум 3 символа. Попробуйте еще раз:")
        return
    
    await state.update_data(title=title)
    await state.set_state(NotificationStates.waiting_for_recipient_type)
    
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Все пользователи")],
        [KeyboardButton(text="Только с активными подписками")],
        [KeyboardButton(text="Только с истекшими подписками")],
        [KeyboardButton(text="Новые пользователи (за 7 дней)")],
        [KeyboardButton(text="Только администраторы")],
        [KeyboardButton(text="Отмена")]
    ], resize_keyboard=True)
    
    await message.answer(
        f"📋 <b>Заголовок:</b> {title}\n\n"
        "Выберите тип получателей:",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.message(NotificationStates.waiting_for_recipient_type)
async def notification_recipient_type_handler(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отправка уведомления отменена.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return
    
    recipient_type_map = {
        "Все пользователи": "all",
        "Только с активными подписками": "active",
        "Только с истекшими подписками": "expired",
        "Новые пользователи (за 7 дней)": "new",
        "Только администраторы": "admins"
    }
    
    recipient_type = recipient_type_map.get(message.text)
    if not recipient_type:
        await message.answer("Пожалуйста, выберите тип получателей из списка:")
        return
    
    await state.update_data(recipient_type=recipient_type)
    await state.set_state(NotificationStates.waiting_for_message)
    
    await message.answer(
        f"📋 <b>Заголовок:</b> {(await state.get_data())['title']}\n"
        f"👥 <b>Получатели:</b> {message.text}\n\n"
        "Введите текст сообщения:\n\n"
        "<i>Подпись 'С уважением, команда разработки SeaVPN' будет добавлена автоматически.</i>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    )

@dp.message(NotificationStates.waiting_for_message)
async def notification_message_handler(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Отправка уведомления отменена.", reply_markup=get_main_menu_keyboard(is_admin=is_admin(message.from_user.id)))
        return
    
    message_text = message.text.strip()
    if len(message_text) < 5:
        await message.answer("Сообщение должно содержать минимум 5 символов. Попробуйте еще раз:")
        return
    
    data = await state.get_data()
    title = data['title']
    recipient_type = data['recipient_type']
    
    # Получаем количество получателей
    db = SessionLocal()
    try:
        if recipient_type == 'all':
            count = db.query(User).count()
        elif recipient_type == 'active':
            count = db.query(User).join(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at > datetime.utcnow()
            ).distinct().count()
        elif recipient_type == 'expired':
            count = db.query(User).join(Subscription).filter(
                Subscription.status == "expired"
            ).distinct().count()
        elif recipient_type == 'new':
            week_ago = datetime.utcnow() - timedelta(days=7)
            count = db.query(User).filter(User.created_at >= week_ago).count()
        elif recipient_type == 'admins':
            count = db.query(User).filter(User.telegram_id.in_(ADMIN_IDS)).count()
        else:
            count = 0
    finally:
        db.close()
    
    # Показываем предварительный просмотр
    preview_text = f"📢 <b>Предварительный просмотр уведомления</b>\n\n"
    preview_text += f"<b>{title}</b>\n\n"
    preview_text += f"{message_text}\n\n"
    preview_text += f"<i>С уважением,\nкоманда разработки SeaVPN</i>\n\n"
    preview_text += f"👥 <b>Получателей:</b> {count}\n\n"
    preview_text += "Отправить уведомление?"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data=f"send_notification_{title}_{recipient_type}_{message_text}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_notification")]
    ])
    
    await message.answer(preview_text, parse_mode="HTML", reply_markup=keyboard)
    await state.clear()

# Обработчик callback для отправки уведомления
@dp.callback_query(lambda c: c.data.startswith("send_notification_"))
async def send_notification_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    # Парсим данные из callback
    parts = callback.data.split("_", 3)
    if len(parts) != 4:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    title = parts[1]
    recipient_type = parts[2]
    message_text = parts[3]
    
    # Отправляем уведомление
    try:
        # Получаем список пользователей
        db = SessionLocal()
        try:
            if recipient_type == 'all':
                users = db.query(User).all()
            elif recipient_type == 'active':
                users = db.query(User).join(Subscription).filter(
                    Subscription.status == "active",
                    Subscription.expires_at > datetime.utcnow()
                ).distinct().all()
            elif recipient_type == 'expired':
                users = db.query(User).join(Subscription).filter(
                    Subscription.status == "expired"
                ).distinct().all()
            elif recipient_type == 'new':
                week_ago = datetime.utcnow() - timedelta(days=7)
                users = db.query(User).filter(User.created_at >= week_ago).all()
            elif recipient_type == 'admins':
                users = db.query(User).filter(User.telegram_id.in_(ADMIN_IDS)).all()
            else:
                users = []
        finally:
            db.close()
        
        # Формируем полное сообщение
        full_message = f"<b>{title}</b>\n\n{message_text}\n\n<i>С уважением,\nкоманда разработки SeaVPN</i>"
        
        # Отправляем уведомления
        sent_count = 0
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=full_message,
                    parse_mode="HTML"
                )
                sent_count += 1
                
                # Небольшая задержка между отправками
                if sent_count % 10 == 0:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                print(f"Ошибка отправки уведомления пользователю {user.telegram_id}: {e}")
        
        await callback.message.edit_text(
            f"✅ <b>Уведомление отправлено!</b>\n\n"
            f"📋 <b>Заголовок:</b> {title}\n"
            f"👥 <b>Получателей:</b> {sent_count}/{len(users)}\n\n"
            f"Уведомление успешно доставлено {sent_count} пользователям.",
            parse_mode="HTML"
        )
        
    except Exception as e:
        print(f"Ошибка отправки массового уведомления: {e}")
        await callback.message.edit_text(
            "❌ <b>Ошибка отправки уведомления</b>\n\n"
            f"Произошла ошибка: {str(e)}",
            parse_mode="HTML"
        )

@dp.callback_query(lambda c: c.data == "cancel_notification")
async def cancel_notification_callback(callback: CallbackQuery):
    await callback.message.edit_text("❌ Отправка уведомления отменена.")
    await callback.answer()

# Функция запуска бота
async def main():
    global notification_manager
    
    print("Бот запущен...")
    print("Планировщик уведомлений запущен...")
    
    try:
        # Запускаем планировщик уведомлений в фоне
        asyncio.create_task(run_notification_scheduler())
        
        # Запускаем бота
        await dp.start_polling(bot)
    finally:
        await xui_client.close()

if __name__ == "__main__":
    asyncio.run(main())
