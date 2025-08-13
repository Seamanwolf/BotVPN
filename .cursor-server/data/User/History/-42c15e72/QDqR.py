import asyncio
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, Contact
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


from config import BOT_TOKEN, TARIFFS
from database import SessionLocal, User, Subscription, create_tables

# Состояния для FSM
class RegistrationStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_name = State()

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Клавиатуры
def get_contact_keyboard():
    """Клавиатура для запроса контакта"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться номером ☎️", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

def get_main_menu_keyboard():
    """Главное меню"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Профиль"), KeyboardButton(text="Мои ключи")],
            [KeyboardButton(text="Купить ключ"), KeyboardButton(text="Помощь")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_tariffs_keyboard():
    """Клавиатура с тарифами"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"1 месяц - {TARIFFS['1m']['price']}₽")],
            [KeyboardButton(text=f"3 месяца - {TARIFFS['3m']['price']}₽")],
            [KeyboardButton(text="Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Валидация email
def is_valid_email(email: str) -> bool:
    try:
        validate_email(email)
        return True
    except EmailNotValidError:
        return False

# Получение пользователя из БД
async def get_user(telegram_id: int) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        return user
    finally:
        db.close()

# Сохранение пользователя в БД
async def save_user(telegram_id: int, phone: str, full_name: str) -> User:
    db = SessionLocal()
    try:
        user = User(
            telegram_id=telegram_id,
            phone=phone,
            email=None,  # Email больше не требуется
            full_name=full_name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()

# Обработчик команды /start
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    
    if user:
        # Пользователь уже зарегистрирован
        await message.answer(
            f"С возвращением, {user.full_name}! 👋\n\nВыберите действие:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        # Новая регистрация
        await state.set_state(RegistrationStates.waiting_for_contact)
        await message.answer(
            "Добро пожаловать! 🚀\n\nДля регистрации поделитесь своим номером телефона:",
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
    
    # Сохраняем пользователя
    user = await save_user(message.from_user.id, phone, full_name)
    
    await state.clear()
    
    await message.answer(
        f"Регистрация завершена! 🎉\n\nДобро пожаловать, {full_name}!\n\nВыберите действие:",
        reply_markup=get_main_menu_keyboard()
    )

# Обработчик главного меню
@dp.message(F.text.in_(["Профиль", "Мои ключи", "Купить ключ", "Помощь"]))
async def main_menu_handler(message: Message):
    user = await get_user(message.from_user.id)
    
    if not user:
        await message.answer("Пожалуйста, сначала зарегистрируйтесь. Нажмите /start")
        return
    
    if message.text == "Профиль":
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
            f"Телефон: {user.phone}\n"
            f"Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}"
            f"{subscription_info}",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif message.text == "Мои ключи":
        # Получаем активную подписку и конфигурацию
        db = SessionLocal()
        try:
            active_subscription = db.query(Subscription).filter(
                Subscription.user_id == user.id,
                Subscription.status == "active"
            ).first()
            
            if active_subscription and active_subscription.xui_config:
                await message.answer(
                    f"🔑 Ваши ключи\n\n"
                    f"Тариф: {active_subscription.plan}\n"
                    f"Действует до: {active_subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
                    f"Конфигурация:\n`{active_subscription.xui_config}`",
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                await message.answer(
                    "У вас нет активных ключей. Купите подписку в разделе 'Купить ключ'.",
                    reply_markup=get_main_menu_keyboard()
                )
        finally:
            db.close()
    
    elif message.text == "Купить ключ":
        await message.answer(
            "💳 Выберите тариф:\n\n"
            f"• 1 месяц - {TARIFFS['1m']['price']}₽\n"
            f"• 3 месяца - {TARIFFS['3m']['price']}₽",
            reply_markup=get_tariffs_keyboard()
        )
    
    elif message.text == "Помощь":
        await message.answer(
            "❓ Помощь\n\n"
            "• Для технической поддержки: @support\n"
            "• Инструкции по настройке придут после покупки\n"
            "• Время работы поддержки: 24/7\n\n"
            "Если у вас есть вопросы, не стесняйтесь обращаться!",
            reply_markup=get_main_menu_keyboard()
        )

# Обработчик выбора тарифа
@dp.message(F.text.contains("месяц"))
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
    else:
        await message.answer("Неизвестный тариф. Выберите из списка:", reply_markup=get_tariffs_keyboard())
        return
    
    if message.text == "Назад":
        await message.answer("Выберите действие:", reply_markup=get_main_menu_keyboard())
        return
    
    # Демо-версия: создаем тестовую конфигурацию
    demo_config = f"vless://demo-user@user_{user.telegram_id}.local:443?type=tcp&security=reality&sni=example.com&fp=chrome&pbk=demo-key&sid=123456&spx=%2F#user_{user.telegram_id}"
    
    # Сохраняем подписку в БД
    db = SessionLocal()
    try:
        subscription = Subscription(
            user_id=user.id,
            plan=tariff,
            status="active",
            expires_at=datetime.utcnow() + timedelta(days=30*months),
            xui_config=demo_config
        )
        db.add(subscription)
        db.commit()
        
        await message.answer(
            f"✅ Подписка активирована! (ДЕМО-РЕЖИМ)\n\n"
            f"Тариф: {TARIFFS[tariff]['name']}\n"
            f"Стоимость: {price}₽\n"
            f"Действует до: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
            f"Ваша конфигурация (тестовая):\n`{demo_config}`\n\n"
            f"⚠️ Это демо-версия. В реальной версии здесь будет настоящая конфигурация от 3xUI.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    finally:
        db.close()

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

# Функция запуска бота
async def main():
    # Создаем таблицы в БД
    create_tables()
    
    print("Демо-бот запущен...")
    print("⚠️  Это демо-версия без интеграции с 3xUI")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка запуска бота: {e}")

if __name__ == "__main__":
    asyncio.run(main())
