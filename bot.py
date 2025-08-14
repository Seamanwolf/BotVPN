import asyncio
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, Contact, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json


from config import BOT_TOKEN, TARIFFS, REFERRAL_BONUS, BONUS_TO_SUBSCRIPTION, SUPPORT_BOT, ADMIN_IDS
from database import SessionLocal, User, Subscription, Admin, AdminSettings, Payment, generate_referral_code, get_user_by_referral_code, check_telegram_id_exists, check_email_exists
from xui_client import XUIClient
from yookassa_client import YooKassaClient
from notifications import NotificationManager, run_notification_scheduler

# Состояния для FSM
class RegistrationStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_name = State()
    waiting_for_email = State()

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Клиент 3xUI
xui_client = XUIClient()

# Клиент ЮKassa
yookassa_client = YooKassaClient()

# Менеджер уведомлений
notification_manager = None

# Клавиатуры
def get_contact_keyboard():
    """Клавиатура для запроса контакта"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться номером ☎️", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_main_menu_keyboard(is_admin=False):
    """Главное меню"""
    keyboard_buttons = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🔑 Мои ключи")],
        [KeyboardButton(text="💳 Купить ключ"), KeyboardButton(text="🎁 Реферальная система")],
        [KeyboardButton(text="❓ Помощь")]
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
async def save_user(telegram_id: int, phone: str, full_name: str, email: str = None, referral_code: str = None) -> User:
    db = SessionLocal()
    try:
        # Проверяем уникальность Telegram ID
        if check_telegram_id_exists(telegram_id):
            raise ValueError(f"Пользователь с Telegram ID {telegram_id} уже существует")
        
        # Проверяем уникальность email (если передан)
        if email and check_email_exists(email):
            raise ValueError(f"Пользователь с email {email} уже существует")
        
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
            phone=phone,
            email=email,
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
        
        await state.set_state(RegistrationStates.waiting_for_contact)
        await state.update_data(referral_code=referral_code)
        
        welcome_text = "Добро пожаловать! 🚀\n\nДля регистрации поделитесь своим номером телефона:"
        
        await message.answer(
            welcome_text,
            reply_markup=get_contact_keyboard()
        )

# Обработчик получения контакта
@dp.message(RegistrationStates.waiting_for_contact, F.contact)
async def contact_handler(message: Message, state: FSMContext):
    contact: Contact = message.contact
    
    # Проверяем, что контакт принадлежит пользователю
    if contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, поделитесь своим собственным номером телефона.")
        return
    
    # Сохраняем номер телефона
    await state.update_data(phone=contact.phone_number)
    await state.set_state(RegistrationStates.waiting_for_name)
    
    await message.answer(
        "Отлично! Теперь введите ваше имя:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    )



# Обработчик ввода имени
@dp.message(RegistrationStates.waiting_for_name)
async def name_handler(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Регистрация отменена. Нажмите /start для начала.", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True))
        return
    
    full_name = message.text.strip()
    
    if len(full_name) < 2:
        await message.answer("Имя должно содержать минимум 2 символа. Попробуйте еще раз:")
        return
    
    # Получаем данные
    data = await state.get_data()
    phone = data.get("phone")
    referral_code = data.get("referral_code")
    
    # Сохраняем имя и переходим к вводу email
    await state.update_data(full_name=full_name)
    await state.set_state(RegistrationStates.waiting_for_email)
    
    await message.answer(
        "Отлично! Теперь введите ваш email:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    )

# Обработчик ввода email
@dp.message(RegistrationStates.waiting_for_email)
async def email_handler(message: Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Регистрация отменена. Нажмите /start для начала.", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True))
        return
    
    email = message.text.strip()
    
    # Простая валидация email
    if "@" not in email or "." not in email:
        await message.answer("Пожалуйста, введите корректный email адрес:")
        return
    
    # Проверяем уникальность email
    if check_email_exists(email):
        await message.answer("Этот email уже используется. Пожалуйста, введите другой email:")
        return
    
    # Получаем данные
    data = await state.get_data()
    phone = data.get("phone")
    full_name = data.get("full_name")
    referral_code = data.get("referral_code")
    
    # Сохраняем пользователя
    try:
        user = await save_user(message.from_user.id, phone, full_name, email, referral_code)
        
        await state.clear()
        
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
                f"📱 Телефон: {phone}\n"
                f"📧 Email: {email or 'Не указан'}\n"
                f"🎁 Бонусные монеты: {user.bonus_coins}\n"
                f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            await send_admin_notification(notification_text)
    except ValueError as e:
        await message.answer(
            f"❌ Ошибка регистрации: {str(e)}\n\nПопробуйте еще раз или обратитесь в поддержку.",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True)
        )

# Обработчик главного меню
@dp.message(F.text.in_(["👤 Профиль", "🔑 Мои ключи", "💳 Купить ключ", "🎁 Реферальная система", "❓ Помощь", "⚙️ Админ-панель"]))
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
            f"Email: {user.email or 'Не указан'}\n"
            f"Телефон: {user.phone}\n"
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
            "💳 Выберите тариф:\n\n"
            f"• 1 месяц - {TARIFFS['1m']['price']}₽\n"
            f"• 3 месяца - {TARIFFS['3m']['price']}₽",
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
            
            referral_text = f"🎁 Реферальная система\n\n"
            referral_text += f"Ваш реферальный код: `{user.referral_code}`\n"
            referral_text += f"Ваша реферальная ссылка:\n`https://t.me/{bot_username}?start={user.referral_code}`\n\n"
            referral_text += f"Приглашено пользователей: {referrals_count}\n"
            referral_text += f"Бонусных монет: {user.bonus_coins} 🪙\n\n"
            referral_text += f"💰 За каждого приглашенного пользователя вы получаете {REFERRAL_BONUS} монет\n"
            referral_text += f"💎 {BONUS_TO_SUBSCRIPTION} монет = 1 месяц подписки\n"
            referral_text += f"💎 {BONUS_TO_SUBSCRIPTION * 3} монет = 3 месяца подписки\n\n"
            
            # Формируем кнопки в зависимости от количества бонусов
            keyboard_buttons = []
            
            if user.bonus_coins >= BONUS_TO_SUBSCRIPTION * 3:
                keyboard_buttons.append([KeyboardButton(text="💳 Купить 3 месяца за 450 монет")])
                keyboard_buttons.append([KeyboardButton(text="💳 Купить 1 месяц за 150 монет")])
            elif user.bonus_coins >= BONUS_TO_SUBSCRIPTION:
                keyboard_buttons.append([KeyboardButton(text="💳 Купить 1 месяц за 150 монет")])
            else:
                referral_text += f"📈 До обмена на подписку: {BONUS_TO_SUBSCRIPTION - user.bonus_coins} монет"
            
            keyboard_buttons.append([KeyboardButton(text="Назад")])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=keyboard_buttons,
                resize_keyboard=True
            )
            
            await message.answer(
                referral_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        finally:
            db.close()
    
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
        help_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">FoxRay</a>\n"
        help_text += "• <a href=\"https://github.com/yichengchen/clashX/releases\">ClashX</a>\n\n"
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
@dp.message(F.text.contains("месяц") | F.text.contains("Купить тест"))
async def tariff_handler(message: Message):
    user = await get_user(message.from_user.id)
    
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    if "1 месяц" in message.text:
        tariff = "1m"
        price = TARIFFS["1m"]["price"]
        days = TARIFFS["1m"]["days"]
    elif "3 месяца" in message.text:
        tariff = "3m"
        price = TARIFFS["3m"]["price"]
        days = TARIFFS["3m"]["days"]
    elif "Купить тест" in message.text:
        tariff = "test"
        price = TARIFFS["test"]["price"]
        days = TARIFFS["test"]["days"]
    else:
        await message.answer("Неизвестный тариф. Выберите из списка:", reply_markup=get_tariffs_keyboard(is_admin(message.from_user.id)))
        return
    
    if message.text == "Назад":
        await message.answer("Выберите действие:", reply_markup=get_user_keyboard(message.from_user.id))
        return
    
    # Для всех тарифов (включая тестовый) - создаем платеж в ЮKassa
    await create_payment_for_tariff(message, user, tariff, price, days)

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
@dp.message(F.text.in_(["💳 Купить 1 месяц за 150 монет", "💳 Купить 3 месяца за 450 монет"]))
async def exchange_bonus_handler(message: Message):
    user = await get_user(message.from_user.id)
    
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    # Определяем тариф и стоимость
    if message.text == "💳 Купить 1 месяц за 150 монет":
        required_coins = BONUS_TO_SUBSCRIPTION
        months = 1
        tariff_name = "1 месяц (за бонусы)"
    elif message.text == "💳 Купить 3 месяца за 450 монет":
        required_coins = BONUS_TO_SUBSCRIPTION * 3
        months = 3
        tariff_name = "3 месяца (за бонусы)"
    else:
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
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">FoxRay</a>\n"
                    apps_text += "• <a href=\"https://github.com/yichengchen/clashX/releases\">ClashX</a>\n\n"
                    
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

# Обработчик для всех сообщений в состоянии регистрации (кроме специальных)
@dp.message(RegistrationStates.waiting_for_contact)
async def registration_contact_handler(message: Message, state: FSMContext):
    if message.text == "/start":
        await start_handler(message, state)
    else:
        await message.answer(
            "Пожалуйста, поделитесь своим номером телефона, нажав на кнопку ниже:",
            reply_markup=get_contact_keyboard()
        )

@dp.message(RegistrationStates.waiting_for_name)
async def registration_name_handler(message: Message, state: FSMContext):
    if message.text == "/start":
        await start_handler(message, state)
    else:
        await message.answer(
            "Пожалуйста, введите ваше имя или нажмите 'Отмена':",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        )

@dp.message(RegistrationStates.waiting_for_email)
async def registration_email_handler(message: Message, state: FSMContext):
    if message.text == "/start":
        await start_handler(message, state)
    else:
        await message.answer(
            "Пожалуйста, введите ваш email или нажмите 'Отмена':",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
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
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">FoxRay</a>\n"
                    apps_text += "• <a href=\"https://github.com/yichengchen/clashX/releases\">ClashX</a>\n\n"
                    
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
            if tariff == "test":
                days = TARIFFS["test"]["days"]
                tariff_name = TARIFFS["test"]["name"]
            elif tariff == "1m":
                days = TARIFFS["1m"]["days"]
                tariff_name = TARIFFS["1m"]["name"]
            elif tariff == "3m":
                days = TARIFFS["3m"]["days"]
                tariff_name = TARIFFS["3m"]["name"]
            else:
                await callback.answer("❌ Неизвестный тариф", show_alert=True)
                return
            
            # Создаем подписку в 3xUI
            user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
            
            # Определяем следующий номер подписки
            existing_subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
            next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
            
            xui_result = await xui_client.create_user(
                user_email, 
                days, 
                f"{user.full_name} (PAID)", 
                str(user.telegram_id), 
                next_subscription_number
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
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">FoxRay</a>\n"
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
