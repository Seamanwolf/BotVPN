#!/usr/bin/env python3
"""
SeaVPN Support Bot - бот для технической поддержки пользователей SeaVPN
"""

import asyncio
import logging
from datetime import datetime, timedelta
import os
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения или из аргументов
BOT_TOKEN = os.getenv("SUPPORT_BOT_TOKEN", "8261852911:AAHFkocNITb8VDYZnjyQ_Wcy7A25oLANwtY")

# ID администраторов
ADMIN_IDS = [5379158583]  # Замените на свой ID

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class SupportStates(StatesGroup):
    waiting_for_issue = State()
    waiting_for_reply = State()

# Структура для хранения тикетов
tickets = {}

# Клавиатуры
def get_main_keyboard(is_admin=False):
    """Главное меню"""
    keyboard = [
        [KeyboardButton(text="📝 Создать тикет"), KeyboardButton(text="🔍 Мои тикеты")]
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
    return user_id in ADMIN_IDS

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

@dp.message(SupportStates.waiting_for_issue)
async def process_issue(message: Message, state: FSMContext):
    """Обработка описания проблемы"""
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    issue_text = message.text
    
    # Генерируем уникальный ID тикета
    ticket_id = f"{len(tickets) + 1:04d}"
    
    # Сохраняем тикет
    tickets[ticket_id] = {
        "id": ticket_id,
        "user_id": user_id,
        "user_name": user_name,
        "issue": issue_text,
        "status": "open",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": [
            {
                "from_user": user_id,
                "text": issue_text,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        ]
    }
    
    # Отправляем подтверждение пользователю
    await message.answer(
        f"✅ Ваш тикет #{ticket_id} успешно создан!\n\n"
        f"Мы рассмотрим вашу проблему в ближайшее время и ответим вам.\n"
        f"Вы можете проверить статус вашего тикета в разделе 'Мои тикеты'.",
        reply_markup=get_main_keyboard(is_admin=is_admin(user_id))
    )
    
    # Отправляем уведомление администраторам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📢 **Новый тикет #{ticket_id}**\n\n"
                f"От: {user_name} (ID: {user_id})\n"
                f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Сообщение:\n{issue_text}",
                reply_markup=get_ticket_keyboard(ticket_id)
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
    
    await state.clear()

@dp.message(F.text == "🔍 Мои тикеты")
async def my_tickets_handler(message: Message):
    """Обработчик просмотра своих тикетов"""
    user_id = message.from_user.id
    
    # Фильтруем тикеты пользователя
    user_tickets = {tid: ticket for tid, ticket in tickets.items() if ticket["user_id"] == user_id}
    
    if not user_tickets:
        await message.answer(
            "У вас пока нет активных тикетов.\n"
            "Чтобы создать тикет, нажмите кнопку '📝 Создать тикет'."
        )
        return
    
    # Формируем сообщение со списком тикетов
    response = "🔍 **Ваши тикеты:**\n\n"
    
    for tid, ticket in user_tickets.items():
        status_emoji = "🟢" if ticket["status"] == "open" else "🔴"
        response += f"{status_emoji} **Тикет #{tid}**\n"
        response += f"Статус: {'Открыт' if ticket['status'] == 'open' else 'Закрыт'}\n"
        response += f"Создан: {ticket['created_at']}\n"
        response += f"Сообщений: {len(ticket['messages'])}\n\n"
        
        # Добавляем кнопку для просмотра тикета
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 Просмотреть", callback_data=f"view_ticket:{tid}")]
        ])
        
        await message.answer(response, reply_markup=keyboard)
        response = ""  # Сбрасываем сообщение для следующего тикета

@dp.callback_query(lambda c: c.data.startswith("view_ticket:"))
async def view_ticket_callback(callback: CallbackQuery):
    """Обработчик просмотра тикета"""
    ticket_id = callback.data.split(":")[1]
    
    if ticket_id not in tickets:
        await callback.answer("Тикет не найден")
        return
    
    ticket = tickets[ticket_id]
    user_id = callback.from_user.id
    
    # Проверяем, что тикет принадлежит пользователю или пользователь - админ
    if ticket["user_id"] != user_id and not is_admin(user_id):
        await callback.answer("У вас нет доступа к этому тикету")
        return
    
    # Формируем сообщение с историей переписки
    response = f"📝 **Тикет #{ticket_id}**\n"
    response += f"Статус: {'🟢 Открыт' if ticket['status'] == 'open' else '🔴 Закрыт'}\n"
    response += f"Создан: {ticket['created_at']}\n\n"
    
    for i, msg in enumerate(ticket["messages"]):
        sender = "👤 Вы" if msg["from_user"] == user_id else "👨‍💻 Поддержка"
        response += f"{sender} ({msg['time']}):\n{msg['text']}\n\n"
    
    # Добавляем кнопки действий
    keyboard = None
    if ticket["status"] == "open":
        if is_admin(user_id):
            keyboard = get_ticket_keyboard(ticket_id)
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Ответить", callback_data=f"reply_ticket:{ticket_id}")]
            ])
    
    await callback.message.edit_text(response, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("reply_ticket:"))
async def reply_ticket_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик ответа на тикет"""
    ticket_id = callback.data.split(":")[1]
    
    if ticket_id not in tickets:
        await callback.answer("Тикет не найден")
        return
    
    ticket = tickets[ticket_id]
    
    if ticket["status"] != "open":
        await callback.answer("Этот тикет закрыт и не может быть обновлен")
        return
    
    await state.update_data(ticket_id=ticket_id)
    await state.set_state(SupportStates.waiting_for_reply)
    
    await callback.message.answer(
        f"📝 Введите ваш ответ на тикет #{ticket_id}:"
    )
    await callback.answer()

@dp.message(SupportStates.waiting_for_reply)
async def process_reply(message: Message, state: FSMContext):
    """Обработка ответа на тикет"""
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    
    if not ticket_id or ticket_id not in tickets:
        await message.answer("Тикет не найден или был удален")
        await state.clear()
        return
    
    ticket = tickets[ticket_id]
    user_id = message.from_user.id
    reply_text = message.text
    
    # Проверяем, что тикет принадлежит пользователю или пользователь - админ
    if ticket["user_id"] != user_id and not is_admin(user_id):
        await message.answer("У вас нет доступа к этому тикету")
        await state.clear()
        return
    
    # Добавляем ответ в историю сообщений
    ticket["messages"].append({
        "from_user": user_id,
        "text": reply_text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    
    # Отправляем подтверждение
    await message.answer(
        f"✅ Ваш ответ на тикет #{ticket_id} успешно отправлен!",
        reply_markup=get_main_keyboard(is_admin=is_admin(user_id))
    )
    
    # Отправляем уведомление получателю (админу или пользователю)
    recipient_id = ticket["user_id"] if is_admin(user_id) else ADMIN_IDS[0]
    
    try:
        sender_name = "Поддержка" if is_admin(user_id) else message.from_user.full_name
        
        await bot.send_message(
            recipient_id,
            f"📢 **Новый ответ на тикет #{ticket_id}**\n\n"
            f"От: {sender_name}\n"
            f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Сообщение:\n{reply_text}",
            reply_markup=get_ticket_keyboard(ticket_id)
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
    
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("close_ticket:"))
async def close_ticket_callback(callback: CallbackQuery):
    """Обработчик закрытия тикета"""
    ticket_id = callback.data.split(":")[1]
    
    if ticket_id not in tickets:
        await callback.answer("Тикет не найден")
        return
    
    ticket = tickets[ticket_id]
    user_id = callback.from_user.id
    
    # Только админ может закрывать тикеты
    if not is_admin(user_id):
        await callback.answer("У вас нет прав для закрытия тикета")
        return
    
    # Закрываем тикет
    ticket["status"] = "closed"
    
    # Отправляем подтверждение
    await callback.message.edit_text(
        f"🔴 Тикет #{ticket_id} был закрыт.\n\n"
        f"Если у вас возникнут новые вопросы, создайте новый тикет."
    )
    
    # Отправляем уведомление пользователю
    try:
        await bot.send_message(
            ticket["user_id"],
            f"🔴 Ваш тикет #{ticket_id} был закрыт.\n\n"
            f"Если у вас возникнут новые вопросы, создайте новый тикет."
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю: {e}")
    
    await callback.answer("Тикет успешно закрыт")

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
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой функции")
        return
    
    if not tickets:
        await message.answer("Нет активных тикетов")
        return
    
    # Сортируем тикеты: сначала открытые, потом по времени создания (новые вверху)
    sorted_tickets = sorted(
        tickets.values(),
        key=lambda t: (0 if t["status"] == "open" else 1, t["created_at"]),
        reverse=True
    )
    
    for ticket in sorted_tickets[:10]:  # Ограничиваем до 10 тикетов
        status_emoji = "🟢" if ticket["status"] == "open" else "🔴"
        response = f"{status_emoji} **Тикет #{ticket['id']}**\n"
        response += f"От: {ticket['user_name']} (ID: {ticket['user_id']})\n"
        response += f"Статус: {'Открыт' if ticket['status'] == 'open' else 'Закрыт'}\n"
        response += f"Создан: {ticket['created_at']}\n"
        response += f"Сообщений: {len(ticket['messages'])}\n\n"
        
        # Добавляем кнопку для просмотра тикета
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👁 Просмотреть", callback_data=f"view_ticket:{ticket['id']}")]
        ])
        
        await message.answer(response, reply_markup=keyboard)

@dp.message(F.text == "📊 Статистика")
async def statistics_handler(message: Message):
    """Обработчик просмотра статистики (только для админов)"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("У вас нет доступа к этой функции")
        return
    
    # Собираем статистику
    total_tickets = len(tickets)
    open_tickets = sum(1 for t in tickets.values() if t["status"] == "open")
    closed_tickets = total_tickets - open_tickets
    
    # Статистика по пользователям
    users = set(t["user_id"] for t in tickets.values())
    total_users = len(users)
    
    # Статистика по сообщениям
    total_messages = sum(len(t["messages"]) for t in tickets.values())
    
    await message.answer(
        f"📊 **Статистика тикетов**\n\n"
        f"Всего тикетов: {total_tickets}\n"
        f"• Открытых: {open_tickets}\n"
        f"• Закрытых: {closed_tickets}\n\n"
        f"Всего пользователей: {total_users}\n"
        f"Всего сообщений: {total_messages}\n"
    )

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
