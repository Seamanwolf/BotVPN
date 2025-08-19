from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, BigInteger, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import secrets
import string

# Настройки базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://vpn_user:vpn_password@localhost/vpn_bot")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    referral_code = Column(String, unique=True, index=True, nullable=False)
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    bonus_coins = Column(Integer, default=0)
    has_made_first_purchase = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String, nullable=False)  # "1m", "3m", "test", "bonus"
    plan_name = Column(String, nullable=False)
    status = Column(String, default="active")  # "active", "expired", "paused"
    subscription_number = Column(Integer, default=1)  # Уникальный номер подписки для пользователя
    expires_at = Column(DateTime, nullable=False)
    extensions_count = Column(Integer, default=0)  # Количество продлений
    last_extension_date = Column(DateTime, nullable=True)  # Дата последнего продления
    total_days_added = Column(Integer, default=0)  # Общее количество добавленных дней
    created_at = Column(DateTime, default=datetime.utcnow)

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False, default="yookassa")  # Платежный провайдер
    invoice_id = Column(String, nullable=True)  # ID инвойса от провайдера
    amount = Column(Integer, nullable=False)
    currency = Column(String, default="RUB")
    status = Column(String, default="pending")  # "pending", "completed", "failed", "canceled"
    payload = Column(Text, nullable=True)  # Дополнительные данные
    payment_method = Column(String, default="yookassa")
    yookassa_payment_id = Column(String, nullable=True)
    subscription_type = Column(String, nullable=True)  # "1m", "3m", "test"
    description = Column(String, nullable=True)
    payment_type = Column(String, nullable=True)  # "new", "extension" - тип платежа
    payment_metadata = Column(Text, nullable=True)  # JSON метаданные (например, subscription_id для продления)
    receipt_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class Admin(Base):
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    is_superadmin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

class AdminSettings(Base):
    __tablename__ = "admin_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    notifications_enabled = Column(Boolean, default=True)
    new_user_notifications = Column(Boolean, default=True)
    subscription_notifications = Column(Boolean, default=True)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

def generate_referral_code(length=8):
    """Генерация уникального реферального кода"""
    characters = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(characters) for _ in range(length))
        # Проверяем, что код уникален
        db = SessionLocal()
        try:
            existing = db.query(User).filter(User.referral_code == code).first()
            if not existing:
                return code
        finally:
            db.close()

def get_user_by_referral_code(referral_code: str):
    """Получение пользователя по реферальному коду"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.referral_code == referral_code).first()
    finally:
        db.close()

def check_telegram_id_exists(telegram_id: int) -> bool:
    """Проверка существования пользователя по Telegram ID"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        return user is not None
    finally:
        db.close()

def check_email_exists(email: str) -> bool:
    """Проверка существования пользователя по email"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        return user is not None
    finally:
        db.close()

class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="open")  # open, closed
    ticket_type = Column(String, default="support")  # support, suggestion
    subject = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    # Отношения
    user = relationship("User", backref="tickets")
    messages = relationship("TicketMessage", backref="ticket", cascade="all, delete-orphan")

class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL для системных сообщений
    sender_type = Column(String, default="user")  # user, admin, system
    message = Column(Text, nullable=False)
    attachment_type = Column(String, nullable=True)  # photo, video, document
    attachment_file_id = Column(String, nullable=True)  # Telegram file_id
    attachment_url = Column(String, nullable=True)  # URL для скачивания
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    sender = relationship("User", backref="sent_messages")

class AdminReadMessages(Base):
    __tablename__ = "admin_read_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=False)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    last_read_message_id = Column(Integer, ForeignKey("ticket_messages.id"), nullable=False)
    read_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    admin = relationship("Admin", backref="read_messages")
    ticket = relationship("Ticket", backref="admin_reads")
    last_message = relationship("TicketMessage")
