import asyncio
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, Contact, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


from config import BOT_TOKEN, TARIFFS, REFERRAL_BONUS, BONUS_TO_SUBSCRIPTION, SUPPORT_BOT, ADMIN_IDS
from database import SessionLocal, User, Subscription, Admin, AdminSettings, generate_referral_code, get_user_by_referral_code, check_telegram_id_exists, check_email_exists
from xui_client import XUIClient
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

def get_tariffs_keyboard():
    """Клавиатура с тарифами"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"1 месяц - {TARIFFS['1m']['price']}₽")],
            [KeyboardButton(text=f"3 месяца - {TARIFFS['3m']['price']}₽")],
            [KeyboardButton(text="Купить тест (1 день)")],
            [KeyboardButton(text="Назад")]
        ],
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
        
        # Если пользователь пришел по реферальной ссылке, начисляем бонус пригласившему
        if referred_by:
            referrer.bonus_coins += REFERRAL_BONUS
            db.commit()
            
            # Отправляем уведомление о реферальном бонусе
            if notification_manager:
                await notification_manager.notify_referral_bonus(referrer.id, full_name)
        
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
        # Получаем активную подписку и конфигурацию
        db = SessionLocal()
        try:
            # Получаем все подписки пользователя
            user_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id
            ).order_by(Subscription.created_at.desc()).all()
            
            if user_subscriptions:
                message_text = f"🔑 Ваши ключи\n\n"
                
                # Получаем актуальную конфигурацию из 3xUI
                user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
                config = await xui_client.get_user_config(user_email)
                
                # Находим самую новую активную подписку для отображения конфигурации
                active_subscription = None
                for sub in user_subscriptions:
                    days_left = (sub.expires_at - datetime.utcnow()).days
                    if days_left > 0:  # Подписка еще не истекла
                        active_subscription = sub
                        break
                
                # Показываем все подписки
                for subscription in user_subscriptions:
                    days_left = (subscription.expires_at - datetime.utcnow()).days
                    
                    message_text += f"**Ключ #{subscription.key_number}**\n"
                    message_text += f"Тариф: {subscription.plan}\n"
                    message_text += f"Действует до: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
                    
                    # Определяем статус подписки по времени истечения
                    if days_left <= 0:
                        message_text += f"⚠️ Подписка истекла!\n"
                    elif days_left <= 3:
                        message_text += f"⚠️ Подписка истекает через {days_left} дней!\n"
                    elif days_left <= 7:
                        message_text += f"📅 Подписка истекает через {days_left} дней\n"
                    else:
                        message_text += f"✅ Подписка активна\n"
                    
                    message_text += f"ID: {subscription.id}\n\n"
                
                # Показываем конфигурацию только для активной подписки
                if active_subscription and config:
                    message_text += f"**Конфигурация VPN:**\n`{config}`\n\n"
                    message_text += f"📱 **Рекомендуемые приложения:**\n"
                    message_text += f"• Android: V2rayNG, Clash for Android\n"
                    message_text += f"• iPhone: Streisand, Shadowrocket\n"
                    message_text += f"• Windows: Hiddify, V2rayN\n"
                    message_text += f"• Mac: FoxRay, ClashX\n\n"
                    
                    # Кнопки для управления
                    keyboard_buttons = []
                    
                    # Кнопки продления для активной подписки
                    if active_subscription and days_left <= 7:
                        extend_row = []
                        extend_row.append(InlineKeyboardButton(text="💳 Продлить на 1 месяц (149₽)", callback_data=f"extend_1m_{active_subscription.id}"))
                        extend_row.append(InlineKeyboardButton(text="💳 Продлить на 3 месяца (399₽)", callback_data=f"extend_3m_{active_subscription.id}"))
                        keyboard_buttons.append(extend_row)
                        
                        # Кнопки за бонусы если есть достаточно монет
                        if user.bonus_coins >= 150:
                            bonus_row = []
                            if user.bonus_coins >= 150:
                                bonus_row.append(InlineKeyboardButton(text="🪙 Продлить на 1 месяц (150 монет)", callback_data=f"extend_bonus_1m_{active_subscription.id}"))
                            if user.bonus_coins >= 450:
                                bonus_row.append(InlineKeyboardButton(text="🪙 Продлить на 3 месяца (450 монет)", callback_data=f"extend_bonus_3m_{active_subscription.id}"))
                            
                            if bonus_row:
                                keyboard_buttons.append(bonus_row)
                    
                    # Кнопки управления ключами
                    if len(user_subscriptions) > 1:
                        manage_row = []
                        for sub in user_subscriptions:
                            if sub.status == "active":
                                manage_row.append(InlineKeyboardButton(text=f"🗑️ Удалить ключ #{sub.key_number}", callback_data=f"delete_sub_{sub.id}"))
                        if manage_row:
                            keyboard_buttons.append(manage_row)
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
                    await message.answer(
                        message_text,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                else:
                    # Если нет активной подписки или конфигурации
                    await message.answer(
                        message_text + "\n❌ Конфигурация недоступна",
                        parse_mode="Markdown",
                        reply_markup=get_user_keyboard(message.from_user.id)
                    )
            else:
                await message.answer(
                    "У вас нет ключей.",
                    reply_markup=get_user_keyboard(message.from_user.id)
                )
        finally:
            db.close()
    
    elif message.text == "💳 Купить ключ":
        await message.answer(
            "💳 Выберите тариф:\n\n"
            f"• 1 месяц - {TARIFFS['1m']['price']}₽\n"
            f"• 3 месяца - {TARIFFS['3m']['price']}₽",
            reply_markup=get_tariffs_keyboard()
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
        help_text += f"• Для технической поддержки: t.me/{SUPPORT_BOT}\n"
        help_text += "• Время работы поддержки: 24/7\n\n"
        help_text += "📱 Как подключить VPN:\n\n"
        help_text += "**Для Android:**\n"
        help_text += "• V2rayNG: https://play.google.com/store/apps/details?id=com.v2ray.ang\n"
        help_text += "• Clash for Android: https://play.google.com/store/apps/details?id=com.github.kr328.clash\n\n"
        help_text += "**Для iPhone:**\n"
        help_text += "• Streisand: https://apps.apple.com/app/streisand/id6450534064\n"
        help_text += "• Shadowrocket: https://apps.apple.com/app/shadowrocket/id932747118\n\n"
        help_text += "**Для Windows:**\n"
        help_text += "• Hiddify: https://github.com/hiddify/hiddify-next/releases\n"
        help_text += "• V2rayN: https://github.com/2dust/v2rayN/releases\n\n"
        help_text += "**Для Mac:**\n"
        help_text += "• FoxRay: https://github.com/hiddify/hiddify-next/releases\n"
        help_text += "• ClashX: https://github.com/yichengchen/clashX/releases\n\n"
        help_text += "**Инструкция по подключению:**\n"
        help_text += "1. Скачайте приложение для вашей платформы\n"
        help_text += "2. Скопируйте подписочную ссылку из раздела '🔑 Мои ключи'\n"
        help_text += "3. Вставьте ссылку в приложение\n"
        help_text += "4. Нажмите 'Подключить'\n\n"
        help_text += "Если у вас есть вопросы, не стесняйтесь обращаться!"
        
        await message.answer(
            help_text,
            parse_mode="Markdown",
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
        months = TARIFFS["1m"]["months"]
    elif "3 месяца" in message.text:
        tariff = "3m"
        price = TARIFFS["3m"]["price"]
        months = TARIFFS["3m"]["months"]
    elif "Купить тест" in message.text:
        tariff = "test"
        price = 0  # Бесплатный тест
        months = 0  # 1 день
    else:
        await message.answer("Неизвестный тариф. Выберите из списка:", reply_markup=get_tariffs_keyboard())
        return
    
    if message.text == "Назад":
        await message.answer("Выберите действие:", reply_markup=get_user_keyboard(message.from_user.id))
        return
    
    # Создаем пользователя в 3xUI (используем email пользователя)
    try:
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        
        # Для тестового тарифа - 1 день
        if tariff == "test":
            days = 1
        else:
            days = months * 30
            
        xui_result = await xui_client.create_user(user_email, days, f"TG: {user.telegram_id} {user.full_name}", str(user.telegram_id))
        
        if xui_result:
            # Получаем конфигурацию
            config = await xui_client.get_user_config(user_email)
            
            if config:
                # Формируем сообщение в зависимости от тарифа
                if tariff == "test":
                    tariff_name = "Тестовый (1 день)"
                    cost_text = "Бесплатно"
                else:
                    tariff_name = TARIFFS[tariff]['name']
                    cost_text = f"{price}₽"
                
                # Сохраняем подписку в БД
                db = SessionLocal()
                try:
                    # Для тестового тарифа - 1 день
                    if tariff == "test":
                        expires_at = datetime.utcnow() + timedelta(days=1)
                    else:
                        expires_at = datetime.utcnow() + timedelta(days=30*months)
                    
                    # Получаем следующий номер ключа для пользователя
                    from database import get_next_key_number
                    key_number = get_next_key_number(user.id)
                    
                    subscription = Subscription(
                        user_id=user.id,
                        plan=tariff,
                        plan_name=tariff_name,
                        status="active",
                        key_number=key_number,
                        expires_at=expires_at
                    )
                    db.add(subscription)
                    db.commit()
                    
                    # Формируем ссылки на приложения
                    apps_text = "\n📱 **Рекомендуемые приложения:**\n\n"
                    apps_text += "**Android:**\n"
                    apps_text += "• V2rayNG: https://play.google.com/store/apps/details?id=com.v2ray.ang\n"
                    apps_text += "• Clash for Android: https://play.google.com/store/apps/details?id=com.github.kr328.clash\n\n"
                    apps_text += "**iPhone:**\n"
                    apps_text += "• Streisand: https://apps.apple.com/app/streisand/id6450534064\n"
                    apps_text += "• Shadowrocket: https://apps.apple.com/app/shadowrocket/id932747118\n\n"
                    apps_text += "**Windows:**\n"
                    apps_text += "• Hiddify: https://github.com/hiddify/hiddify-next/releases\n"
                    apps_text += "• V2rayN: https://github.com/2dust/v2rayN/releases\n\n"
                    apps_text += "**Mac:**\n"
                    apps_text += "• FoxRay: https://github.com/hiddify/hiddify-next/releases\n"
                    apps_text += "• ClashX: https://github.com/yichengchen/clashX/releases\n\n"
                    
                    await message.answer(
                        f"✅ Подписка активирована!\n\n"
                        f"Тариф: {tariff_name}\n"
                        f"Стоимость: {cost_text}\n"
                        f"Действует до: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"Ваша конфигурация:\n`{config}`\n\n"
                        f"Скопируйте эту ссылку в ваш VPN клиент."
                        f"{apps_text}",
                        parse_mode="Markdown",
                        reply_markup=get_user_keyboard(message.from_user.id)
                    )
                    
                    # Отправляем уведомление о покупке
                    if notification_manager and tariff != "test":
                        await notification_manager.notify_subscription_purchased(user.id, tariff_name, price)
                    
                    # Отправляем уведомление администраторам о покупке подписки
                    settings = get_admin_settings()
                    if settings.notifications_enabled and settings.subscription_notifications:
                        notification_text = (
                            f"💳 **Новая покупка подписки!**\n\n"
                            f"👤 Пользователь: {user.full_name}\n"
                            f"🆔 Telegram ID: {user.telegram_id}\n"
                            f"📧 Email: {user.email or 'Не указан'}\n"
                            f"📦 Тариф: {tariff_name}\n"
                            f"💰 Стоимость: {cost_text}\n"
                            f"📅 Действует до: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
                            f"🕐 Время покупки: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                        )
                        await send_admin_notification(notification_text)
                    
                    # Начисляем реферальный бонус только при первой покупке
                    if user.referred_by and not user.has_made_first_purchase:
                        db = SessionLocal()
                        try:
                            referrer = db.query(User).filter(User.id == user.referred_by).first()
                            if referrer:
                                referrer.bonus_coins += REFERRAL_BONUS
                                
                                # Отмечаем, что пользователь сделал первую покупку
                                user.has_made_first_purchase = True
                                db.merge(user)
                                db.commit()
                                
                                # Отправляем уведомление о реферальном бонусе
                                if notification_manager:
                                    await notification_manager.notify_referral_bonus(referrer.id, user.full_name)
                        finally:
                            db.close()
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
        print(f"Ошибка при создании подписки: {e}")
        await message.answer(
            "Произошла ошибка при создании подписки. Попробуйте позже или обратитесь в поддержку.",
            reply_markup=get_main_menu_keyboard()
        )

# Обработчик синхронизации с 3xUI
@dp.message(F.text == "🔄 Синхронизировать с 3xUI")
async def sync_handler(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    await message.answer("🔄 Синхронизация с 3xUI...")
    
    try:
        # Синхронизируем подписки
        sync_result = await xui_client.sync_subscriptions()
        
        if sync_result["success"]:
            # Проверяем, есть ли активные клиенты для этого пользователя
            user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
            active_clients = sync_result["active_clients"]
            
            user_found = False
            for client in active_clients:
                if client["email"] == user_email:
                    user_found = True
                    break
            
            if user_found:
                # Получаем обновленную конфигурацию
                config = await xui_client.get_user_config(user_email)
                
                if config:
                    await message.answer(
                        f"✅ Синхронизация завершена!\n\n"
                        f"🔗 Обновленная конфигурация:\n`{config}`",
                        parse_mode="Markdown",
                        reply_markup=get_main_menu_keyboard()
                    )
                else:
                    await message.answer(
                        "❌ Конфигурация недоступна после синхронизации",
                        reply_markup=get_main_menu_keyboard()
                    )
            else:
                # Пользователь не найден в 3xUI - возможно, ключ был удален
                await message.answer(
                    "❌ Ваш ключ не найден в 3xUI. Возможно, он был удален.\n\n"
                    "Для восстановления доступа купите новую подписку в разделе 'Купить ключ'.",
                    reply_markup=get_main_menu_keyboard()
                )
        else:
            await message.answer(
                f"❌ Ошибка синхронизации: {sync_result['msg']}",
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
        xui_result = await xui_client.create_user(user_email, days, f"TG: {user.telegram_id} {user.full_name} (BONUS)", str(user.telegram_id))
        
        if xui_result:
            # Получаем конфигурацию
            config = await xui_client.get_user_config(user_email)
            
            if config:
                # Сохраняем подписку в БД
                db = SessionLocal()
                try:
                    # Получаем следующий номер ключа для пользователя
                    from database import get_next_key_number
                    key_number = get_next_key_number(user.id)
                    
                    subscription = Subscription(
                        user_id=user.id,
                        plan="bonus",
                        plan_name=tariff_name,
                        status="active",
                        key_number=key_number,
                        expires_at=datetime.utcnow() + timedelta(days=30*months)
                    )
                    db.add(subscription)
                    
                    # Списываем монеты
                    user.bonus_coins -= required_coins
                    
                    # Обновляем пользователя в базе данных
                    db.merge(user)
                    db.commit()
                    
                    # Формируем ссылки на приложения
                    apps_text = "\n📱 **Рекомендуемые приложения:**\n\n"
                    apps_text += "**Android:**\n"
                    apps_text += "• V2rayNG: https://play.google.com/store/apps/details?id=com.v2ray.ang\n"
                    apps_text += "• Clash for Android: https://play.google.com/store/apps/details?id=com.github.kr328.clash\n\n"
                    apps_text += "**iPhone:**\n"
                    apps_text += "• Streisand: https://apps.apple.com/app/streisand/id6450534064\n"
                    apps_text += "• Shadowrocket: https://apps.apple.com/app/shadowrocket/id932747118\n\n"
                    apps_text += "**Windows:**\n"
                    apps_text += "• Hiddify: https://github.com/hiddify/hiddify-next/releases\n"
                    apps_text += "• V2rayN: https://github.com/2dust/v2rayN/releases\n\n"
                    apps_text += "**Mac:**\n"
                    apps_text += "• FoxRay: https://github.com/hiddify/hiddify-next/releases\n"
                    apps_text += "• ClashX: https://github.com/yichengchen/clashX/releases\n\n"
                    
                    await message.answer(
                        f"✅ Бонусная подписка активирована!\n\n"
                        f"Тариф: {tariff_name}\n"
                        f"Списано монет: {required_coins} 🪙\n"
                        f"Остаток монет: {user.bonus_coins} 🪙\n"
                        f"Действует до: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
                        f"Ваша конфигурация:\n`{config}`\n\n"
                        f"Скопируйте эту ссылку в ваш VPN клиент."
                        f"{apps_text}",
                        parse_mode="Markdown",
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
                            f"🪙 Списано монет: {required_coins}\n"
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
        
        status_text += f"\n🕐 Последнее обновление: {settings.updated_at.strftime('%d.%m.%Y %H:%M')}"
        
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
    
    status_text += f"\n🕐 Последнее обновление: {settings.updated_at.strftime('%d.%m.%Y %H:%M')}"
    
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
        if len(parts) < 3:
            await callback.answer("Ошибка: неверный формат данных")
            return
        
        # Проверяем тип продления (обычное или за бонусы)
        if parts[1] == "bonus":
            is_bonus = True
            tariff = parts[2]  # 1m или 3m
            subscription_id = int(parts[3])
        else:
            is_bonus = False
            tariff = parts[1]  # 1m или 3m
            subscription_id = int(parts[2])
        
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
            if tariff == "1m":
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
            
            # Продлеваем подписку в 3xUI
            user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
            
            # Если подписка истекла, создаем нового пользователя
            if subscription.status == "expired":
                xui_result = await xui_client.create_user(
                    user_email, 
                    days, 
                    f"TG: {user.telegram_id} {user.full_name} (EXTENDED)", 
                    str(user.telegram_id)
                )
            else:
                # Если подписка еще активна, добавляем дни к существующему
                current_expiry = subscription.expires_at
                new_expiry = current_expiry + timedelta(days=days)
                
                # Обновляем в 3xUI (создаем нового пользователя с новым сроком)
                xui_result = await xui_client.create_user(
                    user_email, 
                    days, 
                    f"TG: {user.telegram_id} {user.full_name} (EXTENDED)", 
                    str(user.telegram_id)
                )
            
            if xui_result:
                # Получаем новую конфигурацию
                config = await xui_client.get_user_config(user_email)
                
                if config:
                    # Обновляем подписку в БД
                    if subscription.status == "expired":
                        subscription.expires_at = datetime.utcnow() + timedelta(days=days)
                    else:
                        subscription.expires_at = subscription.expires_at + timedelta(days=days)
                    
                    subscription.status = "active"
                    
                    # Списываем монеты если это продление за бонусы
                    if is_bonus:
                        user.bonus_coins -= required_coins
                        db.merge(user)
                    
                    db.commit()
                    
                    # Формируем ссылки на приложения
                    apps_text = "\n📱 **Рекомендуемые приложения:**\n\n"
                    apps_text += "**Android:**\n"
                    apps_text += "• V2rayNG: https://play.google.com/store/apps/details?id=com.v2ray.ang\n"
                    apps_text += "• Clash for Android: https://play.google.com/store/apps/details?id=com.github.kr328.clash\n\n"
                    apps_text += "**iPhone:**\n"
                    apps_text += "• Streisand: https://apps.apple.com/app/streisand/id6450534064\n"
                    apps_text += "• Shadowrocket: https://apps.apple.com/app/shadowrocket/id932747118\n\n"
                    apps_text += "**Windows:**\n"
                    apps_text += "• Hiddify: https://github.com/hiddify/hiddify-next/releases\n"
                    apps_text += "• V2rayN: https://github.com/2dust/v2rayN/releases\n\n"
                    apps_text += "**Mac:**\n"
                    apps_text += "• FoxRay: https://github.com/hiddify/hiddify-next/releases\n"
                    apps_text += "• ClashX: https://github.com/yichengchen/clashX/releases\n\n"
                    
                    # Формируем сообщение в зависимости от типа продления
                    if is_bonus:
                        cost_text = f"Списано монет: {required_coins} 🪙\nОстаток монет: {user.bonus_coins} 🪙"
                    else:
                        cost_text = f"Стоимость: {price}₽"
                    
                    await callback.message.edit_text(
                        f"✅ Подписка успешно продлена!\n\n"
                        f"Тариф: {tariff_name}\n"
                        f"{cost_text}\n"
                        f"Новая дата окончания: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"Ваша конфигурация:\n`{config}`\n\n"
                        f"Скопируйте эту ссылку в ваш VPN клиент."
                        f"{apps_text}",
                        parse_mode="Markdown"
                    )
                    
                    await callback.answer("Подписка продлена успешно!")
                else:
                    await callback.answer("Ошибка при получении конфигурации")
            else:
                await callback.answer("Ошибка при продлении подписки")
                
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка при продлении подписки: {e}")
        await callback.answer("Произошла ошибка при продлении")

# Обработчик удаления подписки
@dp.callback_query(lambda c: c.data.startswith('delete_sub_'))
async def delete_subscription_handler(callback: CallbackQuery):
    """Обработчик удаления подписки"""
    try:
        # Парсим данные из callback
        subscription_id = int(callback.data.split('_')[2])
        
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
            
            # Показываем предупреждение
            warning_text = (
                f"⚠️ **ВНИМАНИЕ!**\n\n"
                f"Вы собираетесь удалить подписку:\n"
                f"• Ключ #{subscription.key_number}\n"
                f"• Тариф: {subscription.plan}\n"
                f"• Действует до: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"• ID: {subscription.id}\n\n"
                f"**Это действие нельзя отменить!**\n"
                f"• Ключ будет полностью удален\n"
                f"• Средства не возвращаются\n"
                f"• Доступ к VPN прекратится\n\n"
                f"Вы уверены, что хотите удалить эту подписку?"
            )
            
            # Кнопки подтверждения
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
                    InlineKeyboardButton(text="🗑️ Да, удалить!", callback_data=f"confirm_delete_{subscription_id}")
                ]
            ])
            
            await callback.message.edit_text(
                warning_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка при удалении подписки: {e}")
        await callback.answer("Произошла ошибка")

# Обработчик подтверждения удаления
@dp.callback_query(lambda c: c.data.startswith('confirm_delete_'))
async def confirm_delete_handler(callback: CallbackQuery):
    """Обработчик подтверждения удаления подписки"""
    try:
        subscription_id = int(callback.data.split('_')[2])
        
        user = await get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
            if not subscription or subscription.user_id != user.id:
                await callback.answer("Подписка не найдена")
                return
            
            # Удаляем из 3xUI
            user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
            delete_result = await xui_client.delete_user(user_email)
            
            if delete_result:
                # Удаляем из БД
                db.delete(subscription)
                db.commit()
                
                await callback.message.edit_text(
                    f"✅ Подписка успешно удалена!\n\n"
                    f"• Ключ #{subscription.key_number}\n"
                    f"• Тариф: {subscription.plan}\n"
                    f"• ID: {subscription_id}\n\n"
                    f"Ключ больше не активен.",
                    parse_mode="Markdown"
                )
                
                await callback.answer("Подписка удалена!")
            else:
                await callback.answer("Ошибка при удалении из 3xUI")
                
        except Exception as e:
            print(f"Ошибка при удалении подписки: {e}")
            await callback.answer("Произошла ошибка при удалении")
            db.rollback()
        finally:
            db.close()
            
    except Exception as e:
        print(f"Ошибка при подтверждении удаления: {e}")
        await callback.answer("Произошла ошибка")

# Обработчик отмены удаления
@dp.callback_query(lambda c: c.data == "cancel_delete")
async def cancel_delete_handler(callback: CallbackQuery):
    """Обработчик отмены удаления подписки"""
    try:
        # Возвращаемся к списку ключей
        user = await get_user(callback.from_user.id)
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        # Вызываем обработчик "Мои ключи"
        from aiogram.types import Message
        fake_message = Message(
            text="🔑 Мои ключи",
            from_user=callback.from_user,
            chat=callback.message.chat
        )
        await my_keys_handler(fake_message)
        
        # Удаляем сообщение с предупреждением
        await callback.message.delete()
        
    except Exception as e:
        print(f"Ошибка при отмене удаления: {e}")
        await callback.answer("Произошла ошибка")

# Функция запуска бота
async def main():
    global notification_manager
    
    # Инициализируем менеджер уведомлений
    notification_manager = NotificationManager(bot)
    
    print("Бот запущен...")
    print("Планировщик уведомлений запущен...")
    
    try:
        # Запускаем планировщик уведомлений в фоне
        asyncio.create_task(run_notification_scheduler(bot))
        
        # Запускаем бота
        await dp.start_polling(bot)
    finally:
        await xui_client.close()

if __name__ == "__main__":
    asyncio.run(main())
