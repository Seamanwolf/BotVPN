#!/usr/bin/env python3
"""
Модуль для работы с базой данных
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, backref
from datetime import datetime
import secrets
from config import DATABASE_URL

# Создаем движок базы данных
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создаем базовый класс для моделей
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=True)
    full_name = Column(String, nullable=True)
    xui_user_id = Column(String, nullable=True)
    referral_code = Column(String, unique=True, nullable=True)
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    bonus_coins = Column(Integer, default=0)
    has_made_first_purchase = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    subscriptions = relationship("Subscription", back_populates="user")
    referrals = relationship("User", backref=backref("referrer", remote_side=[id]))

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String, nullable=False)  # test, 1m, 3m
    plan_name = Column(String, nullable=False)  # Test, 1 месяц, 3 месяца
    status = Column(String, default="active")  # active, expired
    key_number = Column(Integer, nullable=False)  # Номер ключа для пользователя (1, 2, 3...)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    
    # Отношения
    user = relationship("User", back_populates="subscriptions")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)
    amount = Column(Integer, nullable=False)  # Сумма в копейках
    status = Column(String, default="pending")  # pending, completed, failed
    payment_method = Column(String, nullable=True)  # yoomoney, bonus
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class Admin(Base):
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)  # Telegram username
    full_name = Column(String, nullable=True)  # Полное имя
    password_hash = Column(String, nullable=False)  # Хеш пароля для веб-панели
    is_superadmin = Column(Boolean, default=False)  # Суперадмин
    is_active = Column(Boolean, default=True)  # Активен ли админ
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

class AdminSettings(Base):
    __tablename__ = "admin_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    notifications_enabled = Column(Boolean, default=True)  # Включены ли уведомления
    new_user_notifications = Column(Boolean, default=True)  # Уведомления о новых пользователях
    subscription_notifications = Column(Boolean, default=True)  # Уведомления о покупках
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

def generate_referral_code():
    """Генерация уникального реферального кода"""
    return secrets.token_urlsafe(8)

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
