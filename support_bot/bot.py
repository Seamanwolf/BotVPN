#!/usr/bin/env python3
"""
SeaVPN Support Bot - бот для технической поддержки пользователей SeaVPN
"""

import asyncio
import logging
from datetime import datetime, timedelta
import os
import json
import sys
from aiogram.fsm.context import FSMContext

# Добавляем родительскую директорию в путь для импорта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Импортируем модели базы данных
from database import SessionLocal, User, Subscription, Admin, Ticket, TicketMessage
from config import ADMIN_IDS as CONFIG_ADMIN_IDS

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения или из аргументов
BOT_TOKEN = os.getenv("SUPPORT_BOT_TOKEN", "8261852911:AAHFkocNITb8VDYZnjyQ_Wcy7A25oLANwtY")

# Функция для получения списка ID администраторов из базы данных
def get_admin_ids():
    try:
        db = SessionLocal()
        try:
            # Получаем активных администраторов из базы данных
            admins = db.query(Admin).filter(Admin.is_active == True).all()
            admin_ids = [admin.telegram_id for admin in admins]
            
            # Добавляем администраторов из конфига для совместимости
            admin_ids.extend(CONFIG_ADMIN_IDS)
            
            # Удаляем дубликаты
            admin_ids = list(set(admin_ids))
            
            logger.info(f"Загружено {len(admin_ids)} администраторов: {admin_ids}")
            return admin_ids
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при получении списка администраторов: {e}")
        # Возвращаем администраторов из конфига в случае ошибки
        return CONFIG_ADMIN_IDS

# ID администраторов
ADMIN_IDS = get_admin_ids()

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class SupportStates(StatesGroup):
    waiting_for_issue = State()
    waiting_for_reply = State()
    waiting_for_suggestion = State()

# Функция для генерации номера тикета
def generate_ticket_number():
    db = SessionLocal()
    try:
        # Получаем количество тикетов + 1
        count = db.query(Ticket).count() + 1
        return f"{count:04d}"
    except Exception as e:
        logger.error(f"Ошибка при генерации номера тикета: {e}")
        # В случае ошибки генерируем случайный номер
        import random
        return f"{random.randint(1000, 9999):04d}"
    finally:
        db.close()

# Клавиатуры
def get_main_keyboard(is_admin=False):
    """Главное меню"""
    keyboard = [
        [KeyboardButton(text="📝 Создать тикет"), KeyboardButton(text="🔍 Мои тикеты")],
        [KeyboardButton(text="💡 Предложения")]
    ]
    
    if is_admin:
        keyboard.append([KeyboardButton(text="⚙️ Админ-панель")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard():
    """Клавиатура админа"""
    keyboard = [
        [KeyboardButton(text="📋 Все тикеты"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_ticket_keyboard(ticket_id):
    """Клавиатура для работы с тикетом"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Закрыть тикет", callback_data=f"close_ticket:{ticket_id}")],
        [InlineKeyboardButton(text="📝 Ответить", callback_data=f"reply_ticket:{ticket_id}")]
    ])
    return keyboard

def is_admin(user_id):
    """Проверка является ли пользователь администратором"""
    # Обновляем список администраторов каждые 5 минут
    current_time = datetime.now()
    if not hasattr(is_admin, "last_update") or (current_time - is_admin.last_update).total_seconds() > 300:
        global ADMIN_IDS
        ADMIN_IDS = get_admin_ids()
        is_admin.last_update = current_time
    
    return user_id in ADMIN_IDS

# Инициализация времени последнего обновления
is_admin.last_update = datetime.now()

# Обработчики команд
@dp.message(CommandStart())
async def start_handler(message: Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    
    await message.answer(
        f"👋 Здравствуйте, {user_name}!\n\n"
        f"Добро пожаловать в бот поддержки SeaVPN.\n"
        f"Здесь вы можете задать вопрос или сообщить о проблеме, и наши специалисты помогут вам.\n\n"
        f"Используйте кнопки меню для навигации:",
        reply_markup=get_main_keyboard(is_admin=is_admin(user_id))
    )

@dp.message(Command("help"))
async def help_handler(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        "📌 **Справка по боту поддержки**\n\n"
        "• /start - Начать работу с ботом\n"
        "• /help - Показать эту справку\n"
        "• /new_ticket - Создать новый тикет\n"
        "• /my_tickets - Показать мои тикеты\n\n"
        "Для создания тикета, нажмите кнопку '📝 Создать тикет' и опишите вашу проблему.\n"
        "Наши специалисты ответят вам в ближайшее время."
    )

@dp.message(F.text == "📝 Создать тикет")
async def create_ticket_handler(message: Message, state: FSMContext):
    """Обработчик создания тикета"""
    await message.answer(
        "📝 Пожалуйста, опишите вашу проблему или задайте вопрос.\n"
        "Постарайтесь указать как можно больше деталей, чтобы мы могли быстрее вам помочь."
    )
    await state.set_state(SupportStates.waiting_for_issue)

@dp.message(F.text == "💡 Предложения")
async def suggestion_handler(message: Message, state: FSMContext):
    """Обработчик создания предложения по улучшению"""
    await message.answer(
        "💡 Поделитесь вашими идеями и предложениями по улучшению нашего сервиса.\n"
        "Мы ценим ваше мнение и стремимся сделать наш VPN еще лучше!"
    )
    # Сохраняем тип тикета как "suggestion"
    await state.update_data(ticket_type="suggestion")
    await state.set_state(SupportStates.waiting_for_suggestion)

@dp.message(SupportStates.waiting_for_issue)
async def process_issue(message: Message, state: FSMContext):
    """Обработка описания проблемы"""
    telegram_id = message.from_user.id
    user_name = message.from_user.full_name
    issue_text = message.text
    
    # Создаем тикет типа "support"
    await create_ticket(message, "support", issue_text)
    # После создания тикета сбрасываем состояние
    await state.clear()

@dp.message(SupportStates.waiting_for_suggestion)
async def process_suggestion(message: Message, state: FSMContext):
    """Обработка предложения по улучшению"""
    telegram_id = message.from_user.id
    user_name = message.from_user.full_name
    suggestion_text = message.text
    
    # Создаем тикет типа "suggestion"
    await create_ticket(message, "suggestion", suggestion_text)
    # После создания тикета сбрасываем состояние
    await state.clear()

async def create_ticket(message: Message, ticket_type: str, text: str):
    """Общая функция для создания тикета"""
    telegram_id = message.from_user.id
    user_name = message.from_user.full_name
    
    db = SessionLocal()
    try:
        # Валидация типа тикета
        if ticket_type not in ["support", "suggestion"]:
            logger.error(f"Неверный тип тикета: {ticket_type}")
            await message.answer(
                "❌ Произошла ошибка при создании тикета: неверный тип тикета.",
                reply_markup=get_main_keyboard(is_admin=is_admin(telegram_id))
            )
            # Не пытаемся сбросить состояние, так как оно передается отдельно
            return
        
        # Получаем пользователя из базы данных или создаем нового
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            try:
                # Если пользователь не найден, создаем нового
                from string import ascii_uppercase, digits
                import secrets
                
                # Генерируем уникальный реферальный код
                alphabet = ascii_uppercase + digits
                referral_code = ''.join(secrets.choice(alphabet) for _ in range(6))
                
                user = User(
                    telegram_id=telegram_id,
                    full_name=user_name,
                    referral_code=referral_code
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            except Exception as e:
                logger.error(f"Ошибка при создании пользователя: {e}")
                await message.answer(
                    "❌ Произошла ошибка при регистрации пользователя. Пожалуйста, попробуйте позже.",
                    reply_markup=get_main_keyboard(is_admin=is_admin(telegram_id))
                )
                # Не пытаемся сбросить состояние
                return
        
        try:
            # Генерируем номер тикета
            ticket_number = generate_ticket_number()
            
            # Формируем тему тикета
            subject_prefix = "[Предложение] " if ticket_type == "suggestion" else ""
            subject = subject_prefix + (text[:50] + "..." if len(text) > 50 else text)
            
            # Создаем новый тикет
            ticket = Ticket(
                ticket_number=ticket_number,
                user_id=user.id,
                status="open",
                ticket_type=ticket_type,
                subject=subject
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)
        except Exception as e:
            logger.error(f"Ошибка при создании тикета в БД: {e}")
            await message.answer(
                "❌ Произошла ошибка при создании тикета. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_keyboard(is_admin=is_admin(telegram_id))
            )
            # Не пытаемся сбросить состояние
            return
        
        try:
            # Добавляем первое сообщение
            ticket_message = TicketMessage(
                ticket_id=ticket.id,
                sender_id=user.id,
                sender_type="user",
                message=text
            )
            db.add(ticket_message)
            db.commit()
        except Exception as e:
            logger.error(f"Ошибка при добавлении сообщения тикета: {e}")
            # Тикет уже создан, так что продолжаем
            
        # Отправляем подтверждение пользователю в зависимости от типа тикета
        if ticket_type == "suggestion":
            await message.answer(
                f"✅ Ваше предложение (тикет #{ticket_number}) успешно отправлено!\n\n"
                f"Благодарим за ваш вклад в улучшение нашего сервиса.\n"
                f"Мы обязательно рассмотрим вашу идею и свяжемся с вами при необходимости.",
                reply_markup=get_main_keyboard(is_admin=is_admin(telegram_id))
            )
        else:
            await message.answer(
                f"✅ Ваш тикет #{ticket_number} успешно создан!\n\n"
                f"Мы рассмотрим вашу проблему в ближайшее время и ответим вам.\n"
                f"Вы можете проверить статус вашего тикета в разделе 'Мои тикеты'.",
                reply_markup=get_main_keyboard(is_admin=is_admin(telegram_id))
            )
        
        # Отправляем уведомление администраторам
        admin_notification_sent = False
        for admin_id in ADMIN_IDS:
            try:
                # Отправляем уведомление о новом тикете с более заметным форматированием
                notification_prefix = "🆕 *НОВОЕ ПРЕДЛОЖЕНИЕ" if ticket_type == "suggestion" else "🆕 *НОВЫЙ ТИКЕТ"
                await bot.send_message(
                    admin_id,
                    f"{notification_prefix} #{ticket_number}*\n\n"
                    f"👤 *От:* {user_name} (ID: {telegram_id})\n"
                    f"🕒 *Время:* {ticket.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"💬 *Сообщение:*\n{text}",
                    parse_mode="Markdown",
                    reply_markup=get_ticket_keyboard(ticket_number)
                )
                
                # Отправляем звуковое уведомление
                await bot.send_voice(
                    admin_id,
                    voice="https://raw.githubusercontent.com/SeaVPN/notification-sounds/main/new_ticket.ogg",
                    caption="🔊 Новый тикет от пользователя"
                )
                admin_notification_sent = True
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
                # Продолжаем с другими админами
        
        if not admin_notification_sent:
            logger.warning("Не удалось отправить уведомление ни одному из администраторов")
    
    except Exception as e:
        logger.error(f"Ошибка при создании тикета: {e}")
        await message.answer(
            "❌ Произошла ошибка при создании тикета. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_keyboard(is_admin=is_admin(telegram_id))
        )
    finally:
        db.close()
    
    # Мы убрали вызов state.clear(), так как состояние управляется вызывающим кодом

@dp.message(F.text == "🔍 Мои тикеты")
async def my_tickets_handler(message: Message):
    """Обработчик просмотра своих тикетов"""
    telegram_id = message.from_user.id
    
    db = SessionLocal()
    try:
        # Получаем пользователя из базы данных
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            await message.answer(
                "Вы не зарегистрированы в системе.\n"
                "Чтобы создать тикет, нажмите кнопку '📝 Создать тикет'."
            )
            return
        
        # Получаем тикеты пользователя
        tickets = db.query(Ticket).filter(Ticket.user_id == user.id).order_by(Ticket.created_at.desc()).all()
        
        if not tickets:
            await message.answer(
                "У вас пока нет активных тикетов.\n"
                "Чтобы создать тикет, нажмите кнопку '📝 Создать тикет'."
            )
            return
        
        # Формируем сообщение со списком тикетов
        for ticket in tickets:
            # Получаем количество сообщений
            messages_count = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).count()
            
            status_emoji = "🟢" if ticket.status == "open" else "🔴"
            response = f"{status_emoji} **Тикет #{ticket.ticket_number}**\n"
            response += f"Статус: {'Открыт' if ticket.status == 'open' else 'Закрыт'}\n"
            response += f"Тема: {ticket.subject}\n"
            response += f"Создан: {ticket.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            response += f"Сообщений: {messages_count}\n\n"
            
            # Добавляем кнопку для просмотра тикета
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👁 Просмотреть", callback_data=f"view_ticket:{ticket.ticket_number}")]
            ])
            
            await message.answer(response, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка при получении тикетов: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении тикетов. Пожалуйста, попробуйте позже."
        )
    finally:
        db.close()

@dp.callback_query(lambda c: c.data.startswith("view_ticket:"))
async def view_ticket_callback(callback: CallbackQuery):
    """Обработчик просмотра тикета"""
    ticket_number = callback.data.split(":")[1]
    telegram_id = callback.from_user.id
    
    db = SessionLocal()
    try:
        # Получаем пользователя из базы данных
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        # Получаем тикет по номеру
        ticket = db.query(Ticket).filter(Ticket.ticket_number == ticket_number).first()
        
        if not ticket:
            await callback.answer("Тикет не найден")
            return
        
        # Проверяем, что тикет принадлежит пользователю или пользователь - админ
        if ticket.user_id != user.id and not is_admin(telegram_id):
            await callback.answer("У вас нет доступа к этому тикету")
            return
        
        # Получаем сообщения тикета
        messages = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).order_by(TicketMessage.created_at).all()
        
        # Формируем сообщение с историей переписки
        response = f"📝 **Тикет #{ticket_number}**\n"
        response += f"Статус: {'🟢 Открыт' if ticket.status == 'open' else '🔴 Закрыт'}\n"
        response += f"Создан: {ticket.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for msg in messages:
            # Определяем отправителя
            sender_type = msg.sender_type
            if sender_type == "user" and msg.sender_id == user.id:
                sender = "👤 Вы"
            elif sender_type == "admin":
                sender = "👨‍💻 Поддержка"
            elif sender_type == "system":
                sender = "🤖 Система"
            else:
                sender = "👤 Пользователь"
            
            response += f"{sender} ({msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}):\n{msg.message}\n\n"
        
        # Добавляем кнопки действий
        keyboard = None
        if ticket.status == "open":
            if is_admin(telegram_id):
                keyboard = get_ticket_keyboard(ticket_number)
            else:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Ответить", callback_data=f"reply_ticket:{ticket_number}")]
                ])
        
        await callback.message.edit_text(response, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре тикета: {e}")
        await callback.answer("Произошла ошибка при загрузке тикета")
    finally:
        db.close()

@dp.callback_query(lambda c: c.data.startswith("reply_ticket:"))
async def reply_ticket_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик ответа на тикет"""
    ticket_number = callback.data.split(":")[1]
    telegram_id = callback.from_user.id
    
    db = SessionLocal()
    try:
        # Получаем тикет по номеру
        ticket = db.query(Ticket).filter(Ticket.ticket_number == ticket_number).first()
        
        if not ticket:
            await callback.answer("Тикет не найден")
            return
        
        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            await callback.answer("Пользователь не найден")
            return
        
        # Проверяем, что тикет принадлежит пользователю или пользователь - админ
        if ticket.user_id != user.id and not is_admin(telegram_id):
            await callback.answer("У вас нет доступа к этому тикету")
            return
        
        if ticket.status != "open":
            await callback.answer("Этот тикет закрыт и не может быть обновлен")
            return
        
        # Сохраняем ID тикета и тип отправителя в состоянии
        await state.update_data(ticket_id=ticket.id, ticket_number=ticket_number, 
                               is_admin=is_admin(telegram_id))
        await state.set_state(SupportStates.waiting_for_reply)
        
        await callback.message.answer(
            f"📝 Введите ваш ответ на тикет #{ticket_number}:"
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при подготовке ответа на тикет: {e}")
        await callback.answer("Произошла ошибка при подготовке ответа")
    finally:
        db.close()

@dp.message(SupportStates.waiting_for_reply)
async def process_reply(message: Message, state: FSMContext):
    """Обработка ответа на тикет"""
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket_number = data.get("ticket_number")
    is_admin_reply = data.get("is_admin", False)
    
    if not ticket_id or not ticket_number:
        await message.answer("Тикет не найден или был удален")
        await state.clear()
        return
    
    telegram_id = message.from_user.id
    reply_text = message.text
    
    db = SessionLocal()
    try:
        # Получаем тикет по ID
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        
        if not ticket:
            await message.answer("Тикет не найден или был удален")
            await state.clear()
            return
        
        # Получаем пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            await message.answer("Пользователь не найден")
            await state.clear()
            return
        
        # Проверяем, что тикет принадлежит пользователю или пользователь - админ
        if ticket.user_id != user.id and not is_admin(telegram_id):
            await message.answer("У вас нет доступа к этому тикету")
            await state.clear()
            return
        
        # Определяем тип отправителя
        sender_type = "admin" if is_admin_reply else "user"
        
        # Добавляем сообщение в базу данных
        ticket_message = TicketMessage(
            ticket_id=ticket.id,
            sender_id=user.id,
            sender_type=sender_type,
            message=reply_text
        )
        db.add(ticket_message)
        
        # Обновляем время последнего обновления тикета
        ticket.updated_at = datetime.now()
        
        db.commit()
        
        # Отправляем подтверждение
        await message.answer(
            f"✅ Ваш ответ на тикет #{ticket_number} успешно отправлен!",
            reply_markup=get_main_keyboard(is_admin=is_admin(telegram_id))
        )
        
        # Отправляем уведомление получателю
        try:
            if is_admin_reply:
                # Если ответил админ, отправляем уведомление пользователю
                ticket_owner = db.query(User).filter(User.id == ticket.user_id).first()
                if ticket_owner:
                    recipient_id = ticket_owner.telegram_id
                    sender_name = "Поддержка"
                    
                    # Отправляем уведомление пользователю с более заметным форматированием
                    await bot.send_message(
                        recipient_id,
                        f"🔔 *НОВЫЙ ОТВЕТ НА ВАШ ТИКЕТ #{ticket_number}*\n\n"
                        f"📝 *От:* {sender_name}\n"
                        f"🕒 *Время:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"💬 *Сообщение:*\n{reply_text}",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="👁 Просмотреть тикет", callback_data=f"view_ticket:{ticket_number}")]
                        ])
                    )
                    
                    # Отправляем звуковое уведомление
                    await bot.send_voice(
                        recipient_id,
                        voice="https://raw.githubusercontent.com/SeaVPN/notification-sounds/main/notification.ogg",
                        caption="🔊 Новое сообщение в тикете"
                    )
            else:
                # Если ответил пользователь, отправляем уведомление всем админам
                for admin_id in ADMIN_IDS:
                    sender_name = user.full_name
                    
                    # Отправляем уведомление администратору с более заметным форматированием
                    await bot.send_message(
                        admin_id,
                        f"🔔 *НОВЫЙ ОТВЕТ НА ТИКЕТ #{ticket_number}*\n\n"
                        f"👤 *От:* {sender_name} (ID: {telegram_id})\n"
                        f"🕒 *Время:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"💬 *Сообщение:*\n{reply_text}",
                        parse_mode="Markdown",
                        reply_markup=get_ticket_keyboard(ticket_number)
                    )
                    
                    # Отправляем звуковое уведомление
                    await bot.send_voice(
                        admin_id,
                        voice="https://raw.githubusercontent.com/SeaVPN/notification-sounds/main/admin_notification.ogg",
                        caption="🔊 Новый ответ от пользователя"
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке ответа на тикет: {e}")
        await message.answer("Произошла ошибка при отправке ответа")
    finally:
        db.close()
        await state.clear()

@dp.callback_query(lambda c: c.data.startswith("close_ticket:"))
async def close_ticket_callback(callback: CallbackQuery):
    """Обработчик закрытия тикета"""
    ticket_number = callback.data.split(":")[1]
    telegram_id = callback.from_user.id
    
    # Только админ может закрывать тикеты
    if not is_admin(telegram_id):
        await callback.answer("У вас нет прав для закрытия тикета")
        return
    
    db = SessionLocal()
    try:
        # Получаем тикет по номеру
        ticket = db.query(Ticket).filter(Ticket.ticket_number == ticket_number).first()
        
        if not ticket:
            await callback.answer("Тикет не найден")
            return
        
        # Закрываем тикет
        ticket.status = "closed"
        ticket.closed_at = datetime.now()
        
        # Добавляем системное сообщение о закрытии тикета
        ticket_message = TicketMessage(
            ticket_id=ticket.id,
            sender_id=None,  # Системное сообщение
            sender_type="system",
            message="Тикет был закрыт администратором"
        )
        db.add(ticket_message)
        db.commit()
        
        # Отправляем подтверждение
        await callback.message.edit_text(
            f"🔴 Тикет #{ticket_number} был закрыт.\n\n"
            f"Если у вас возникнут новые вопросы, создайте новый тикет."
        )
        
        # Отправляем уведомление пользователю
        try:
            ticket_owner = db.query(User).filter(User.id == ticket.user_id).first()
            if ticket_owner:
                # Отправляем уведомление о закрытии тикета с более заметным форматированием
                await bot.send_message(
                    ticket_owner.telegram_id,
                    f"🔴 *ВАШ ТИКЕТ #{ticket_number} БЫЛ ЗАКРЫТ*\n\n"
                    f"Если у вас возникнут новые вопросы, создайте новый тикет.",
                    parse_mode="Markdown"
                )
                
                # Отправляем звуковое уведомление
                await bot.send_voice(
                    ticket_owner.telegram_id,
                    voice="https://raw.githubusercontent.com/SeaVPN/notification-sounds/main/ticket_closed.ogg",
                    caption="🔊 Тикет был закрыт"
                )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю: {e}")
        
        await callback.answer("Тикет успешно закрыт")
        
    except Exception as e:
        logger.error(f"Ошибка при закрытии тикета: {e}")
        await callback.answer("Произошла ошибка при закрытии тикета")
    finally:
        db.close()

@dp.message(F.text == "⚙️ Админ-панель")
async def admin_panel_handler(message: Message):
    """Обработчик входа в админ-панель"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к админ-панели")
        return
    
    await message.answer(
        "⚙️ **Админ-панель**\n\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "📋 Все тикеты")
async def all_tickets_handler(message: Message):
    """Обработчик просмотра всех тикетов (только для админов)"""
    telegram_id = message.from_user.id
    
    if not is_admin(telegram_id):
        await message.answer("У вас нет доступа к этой функции")
        return
    
    db = SessionLocal()
    try:
        # Получаем все тикеты, сортируем: сначала открытые, потом по времени создания (новые вверху)
        tickets = db.query(Ticket).order_by(
            Ticket.status,  # Сначала открытые (open < closed)
            Ticket.updated_at.desc()  # Затем по времени обновления (новые вверху)
        ).limit(10).all()
        
        if not tickets:
            await message.answer("Нет активных тикетов")
            return
        
        # Формируем сообщение со списком тикетов
        for ticket in tickets:
            # Получаем пользователя
            user = db.query(User).filter(User.id == ticket.user_id).first()
            user_name = user.full_name if user else "Неизвестный пользователь"
            user_telegram_id = user.telegram_id if user else "Неизвестно"
            
            # Получаем количество сообщений
            messages_count = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).count()
            
            status_emoji = "🟢" if ticket.status == "open" else "🔴"
            response = f"{status_emoji} **Тикет #{ticket.ticket_number}**\n"
            response += f"От: {user_name} (ID: {user_telegram_id})\n"
            response += f"Статус: {'Открыт' if ticket.status == 'open' else 'Закрыт'}\n"
            response += f"Тема: {ticket.subject}\n"
            response += f"Создан: {ticket.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            response += f"Обновлен: {ticket.updated_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            response += f"Сообщений: {messages_count}\n\n"
            
            # Добавляем кнопку для просмотра тикета
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👁 Просмотреть", callback_data=f"view_ticket:{ticket.ticket_number}")]
            ])
            
            await message.answer(response, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка при получении всех тикетов: {e}")
        await message.answer("Произошла ошибка при получении тикетов")
    finally:
        db.close()

@dp.message(F.text == "📊 Статистика")
async def statistics_handler(message: Message):
    """Обработчик просмотра статистики (только для админов)"""
    telegram_id = message.from_user.id
    
    if not is_admin(telegram_id):
        await message.answer("У вас нет доступа к этой функции")
        return
    
    db = SessionLocal()
    try:
        # Собираем статистику
        total_tickets = db.query(Ticket).count()
        open_tickets = db.query(Ticket).filter(Ticket.status == "open").count()
        closed_tickets = db.query(Ticket).filter(Ticket.status == "closed").count()
        
        # Статистика по пользователям
        users_with_tickets = db.query(Ticket.user_id).distinct().count()
        
        # Статистика по сообщениям
        total_messages = db.query(TicketMessage).count()
        
        # Статистика по времени
        today = datetime.now().date()
        tickets_today = db.query(Ticket).filter(
            Ticket.created_at >= datetime.combine(today, datetime.min.time())
        ).count()
        
        messages_today = db.query(TicketMessage).filter(
            TicketMessage.created_at >= datetime.combine(today, datetime.min.time())
        ).count()
        
        # Статистика по времени ответа (среднее время между сообщениями пользователя и админа)
        # Это сложный запрос, который требует более глубокого анализа данных
        # Здесь мы просто считаем общее количество сообщений от админов и пользователей
        admin_messages = db.query(TicketMessage).filter(TicketMessage.sender_type == "admin").count()
        user_messages = db.query(TicketMessage).filter(TicketMessage.sender_type == "user").count()
        
        await message.answer(
            f"📊 **Статистика тикетов**\n\n"
            f"Всего тикетов: {total_tickets}\n"
            f"• Открытых: {open_tickets}\n"
            f"• Закрытых: {closed_tickets}\n\n"
            f"Пользователей с тикетами: {users_with_tickets}\n"
            f"Всего сообщений: {total_messages}\n"
            f"• От пользователей: {user_messages}\n"
            f"• От администраторов: {admin_messages}\n\n"
            f"Сегодня:\n"
            f"• Новых тикетов: {tickets_today}\n"
            f"• Новых сообщений: {messages_today}\n"
        )
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer("Произошла ошибка при получении статистики")
    finally:
        db.close()

@dp.message(F.text == "🔙 Назад")
async def back_handler(message: Message):
    """Обработчик кнопки Назад"""
    user_id = message.from_user.id
    
    await message.answer(
        "Выберите действие:",
        reply_markup=get_main_keyboard(is_admin=is_admin(user_id))
    )

# Функция запуска бота
async def main():
    logger.info("Запуск бота поддержки SeaVPN...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
