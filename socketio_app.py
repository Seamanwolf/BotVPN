# socketio_app.py
import os
from flask_socketio import SocketIO

# Отдельный экземпляр, чтобы не ловить циклические импорты
socketio = SocketIO(
    cors_allowed_origins="*",
    message_queue=os.getenv("REDIS_URL"),  # None, если одиночный процесс
    async_mode='eventlet',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    always_connect=True,
    cors_credentials=True
)
