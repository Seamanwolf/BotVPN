from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    xui_user_id = Column(String, nullable=True)  # ID пользователя в 3xUI
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    subscriptions = relationship("Subscription", back_populates="user")

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan = Column(String, nullable=False)  # '1m' | '3m'
    status = Column(String, nullable=False)  # 'active' | 'expired' | 'pending'
    expires_at = Column(DateTime, nullable=True)
    xui_config = Column(Text, nullable=True)  # Конфигурация от 3xUI
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="subscriptions")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    provider = Column(String, nullable=False)  # 'yoomoney'
    invoice_id = Column(String, nullable=True)
    amount = Column(Integer, nullable=False)  # в копейках
    currency = Column(String, default='RUB')
    status = Column(String, nullable=False)  # pending/success/failed
    payload = Column(Text, nullable=True)  # JSON данные
    created_at = Column(DateTime, default=datetime.utcnow)

def create_tables():
    """Создание таблиц в базе данных"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
