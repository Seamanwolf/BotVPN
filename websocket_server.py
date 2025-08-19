import asyncio
import websockets
import json
import logging
from datetime import datetime, timedelta
from database import SessionLocal, Ticket, User, Subscription, TicketMessage
from sqlalchemy import and_

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище активных соединений
connected_clients = set()

# Счетчики для отслеживания изменений
last_ticket_count = 0
last_user_count = 0
last_subscription_count = 0
last_message_count = 0

async def get_notification_counts():
    """Получает актуальные счетчики уведомлений"""
    try:
        db = SessionLocal()
        try:
            # Новые тикеты (за последние 2 часа)
            two_hours_ago = datetime.utcnow() - timedelta(hours=2)
            new_tickets = db.query(Ticket).filter(Ticket.created_at >= two_hours_ago).count()
            
            # Новые пользователи (за последние 2 часа)
            new_users = db.query(User).filter(User.created_at >= two_hours_ago).count()
            
            # Новые подписки (за последние 2 часа)
            new_subscriptions = db.query(Subscription).filter(Subscription.created_at >= two_hours_ago).count()
            
            # Новые сообщения (за последние 2 часа)
            new_messages = db.query(TicketMessage).filter(TicketMessage.created_at >= two_hours_ago).count()
            
            return {
                'tickets': new_tickets,
                'users': new_users,
                'subscriptions': new_subscriptions,
                'messages': new_messages
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при получении счетчиков: {e}")
        return {'tickets': 0, 'users': 0, 'subscriptions': 0, 'messages': 0}

async def check_notifications():
    """Проверяет новые уведомления и отправляет их клиентам"""
    global last_ticket_count, last_user_count, last_subscription_count, last_message_count
    
    while True:
        try:
            current_counts = await get_notification_counts()
            
            # Проверяем изменения
            if current_counts['tickets'] > last_ticket_count:
                notification = {
                    'type': 'new_ticket',
                    'count': current_counts['tickets'],
                    'sound': 'ticket.wav',
                    'message': f'Новый тикет! Всего новых: {current_counts["tickets"]}'
                }
                await broadcast_notification(notification)
            
            if current_counts['users'] > last_user_count:
                notification = {
                    'type': 'new_user',
                    'count': current_counts['users'],
                    'sound': 'user.wav',
                    'message': f'Новый пользователь! Всего новых: {current_counts["users"]}'
                }
                await broadcast_notification(notification)
            
            if current_counts['subscriptions'] > last_subscription_count:
                notification = {
                    'type': 'new_subscription',
                    'count': current_counts['subscriptions'],
                    'sound': 'subscription.wav',
                    'message': f'Новая подписка! Всего новых: {current_counts["subscriptions"]}'
                }
                await broadcast_notification(notification)
            
            if current_counts['messages'] > last_message_count:
                notification = {
                    'type': 'new_message',
                    'count': current_counts['messages'],
                    'sound': 'message.wav',
                    'message': f'Новое сообщение! Всего новых: {current_counts["messages"]}'
                }
                await broadcast_notification(notification)
            
            # Обновляем счетчики
            last_ticket_count = current_counts['tickets']
            last_user_count = current_counts['users']
            last_subscription_count = current_counts['subscriptions']
            last_message_count = current_counts['messages']
            
        except Exception as e:
            logger.error(f"Ошибка при проверке уведомлений: {e}")
        
        # Проверяем каждые 5 секунд
        await asyncio.sleep(5)

async def broadcast_notification(notification):
    """Отправляет уведомление всем подключенным клиентам"""
    if connected_clients:
        message = json.dumps(notification)
        await asyncio.gather(
            *[client.send(message) for client in connected_clients],
            return_exceptions=True
        )

async def websocket_handler(websocket, path):
    """Обработчик WebSocket соединений"""
    try:
        # Добавляем клиента в список подключенных
        connected_clients.add(websocket)
        logger.info(f"Клиент подключен. Всего клиентов: {len(connected_clients)}")
        
        # Отправляем текущие счетчики при подключении
        current_counts = await get_notification_counts()
        await websocket.send(json.dumps({
            'type': 'initial_counts',
            'counts': current_counts
        }))
        
        # Ожидаем сообщения от клиента
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('type') == 'ping':
                    await websocket.send(json.dumps({'type': 'pong'}))
            except json.JSONDecodeError:
                logger.warning("Получено некорректное JSON сообщение")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info("Клиент отключился")
    except Exception as e:
        logger.error(f"Ошибка в WebSocket обработчике: {e}")
    finally:
        # Удаляем клиента из списка
        connected_clients.discard(websocket)
        logger.info(f"Клиент отключен. Всего клиентов: {len(connected_clients)}")

async def main():
    """Основная функция запуска WebSocket сервера"""
    # Запускаем проверку уведомлений в фоне
    asyncio.create_task(check_notifications())
    
    # Запускаем WebSocket сервер
    server = await websockets.serve(websocket_handler, "0.0.0.0", 8765)
    logger.info("WebSocket сервер запущен на ws://0.0.0.0:8765")
    
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
