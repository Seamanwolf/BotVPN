#!/usr/bin/env python3
"""
Модуль для отправки уведомлений пользователям
"""

import asyncio
from datetime import datetime, timedelta
from typing import List
from database import SessionLocal, User, Subscription
from config import REFERRAL_BONUS, BONUS_TO_SUBSCRIPTION
from xui_client import XUIClient
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class NotificationManager:
    def __init__(self, bot):
        self.bot = bot
    
    async def check_expiring_subscriptions(self):
        """Проверка подписок, которые скоро истекают"""
        db = SessionLocal()
        try:
            # Сначала синхронизируем с 3xUI
            await self.sync_with_xui(db)
            
            # Подписки, которые истекают через 3 дня (только активные)
            three_days_from_now = datetime.utcnow() + timedelta(days=3)
            expiring_soon = db.query(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at <= three_days_from_now,
                Subscription.expires_at > datetime.utcnow()
            ).all()
            
            print(f"Найдено {len(expiring_soon)} подписок, которые истекают в ближайшие 3 дня")
            
            for subscription in expiring_soon:
                user = db.query(User).filter(User.id == subscription.user_id).first()
                if user:
                    days_left = (subscription.expires_at - datetime.utcnow()).days
                    
                    if days_left == 0:
                        # Истекает сегодня
                        message = (
                            f"⚠️ Внимание! Ваша подписка истекает сегодня!\n\n"
                            f"Тариф: {subscription.plan}\n"
                            f"Время истечения: {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                            f"Чтобы продолжить пользоваться VPN, продлите подписку:"
                        )
                        
                        # Кнопки продления
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="💳 Продлить на 1 месяц (149₽)", callback_data=f"extend_1m_{subscription.id}"),
                                InlineKeyboardButton(text="💳 Продлить на 3 месяца (399₽)", callback_data=f"extend_3m_{subscription.id}")
                            ]
                        ])
                    else:
                        # Истекает через несколько дней
                        message = (
                            f"⚠️ Напоминание! Ваша подписка истекает через {days_left} дней\n\n"
                            f"Тариф: {subscription.plan}\n"
                            f"Дата истечения: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
                            f"Чтобы не потерять доступ к VPN, продлите подписку заранее:"
                        )
                        
                        # Кнопки продления
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [
                                InlineKeyboardButton(text="💳 Продлить на 1 месяц (149₽)", callback_data=f"extend_1m_{subscription.id}"),
                                InlineKeyboardButton(text="💳 Продлить на 3 месяца (399₽)", callback_data=f"extend_3m_{subscription.id}")
                            ]
                        ])
                    
                    try:
                        await self.bot.send_message(user.telegram_id, message, reply_markup=keyboard)
                        print(f"Отправлено уведомление об истечении подписки пользователю {user.telegram_id}")
                    except Exception as e:
                        print(f"Ошибка отправки уведомления пользователю {user.telegram_id}: {e}")
            
            # Подписки, которые уже истекли (только активные)
            expired = db.query(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at <= datetime.utcnow()
            ).all()
            
            print(f"Найдено {len(expired)} истекших подписок")
            
            for subscription in expired:
                # Обновляем статус подписки
                subscription.status = "expired"
                
                user = db.query(User).filter(User.id == subscription.user_id).first()
                if user:
                    message = (
                        f"❌ Ваша подписка истекла!\n\n"
                        f"Тариф: {subscription.plan}\n"
                        f"Дата истечения: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
                        f"Для восстановления доступа к VPN продлите подписку:"
                    )
                    
                    # Кнопки продления
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="💳 Продлить на 1 месяц (149₽)", callback_data=f"extend_1m_{subscription.id}"),
                            InlineKeyboardButton(text="💳 Продлить на 3 месяца (399₽)", callback_data=f"extend_3m_{subscription.id}")
                        ]
                    ])
                    
                    try:
                        await self.bot.send_message(user.telegram_id, message, reply_markup=keyboard)
                        print(f"Отправлено уведомление об истечении подписки пользователю {user.telegram_id}")
                    except Exception as e:
                        print(f"Ошибка отправки уведомления пользователю {user.telegram_id}: {e}")
            
            db.commit()
            
        except Exception as e:
            print(f"Ошибка при проверке истекающих подписок: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def sync_with_xui(self, db):
        """Синхронизация подписок с 3xUI"""
        try:
            xui_client = XUIClient()
            sync_result = await xui_client.sync_subscriptions()
            
            if sync_result.get("success"):
                active_clients = sync_result.get("active_clients", [])
                active_emails = [client["email"] for client in active_clients]
                
                # Получаем все активные подписки из БД
                active_subscriptions = db.query(Subscription).filter(
                    Subscription.status == "active"
                ).all()
                
                for subscription in active_subscriptions:
                    user = db.query(User).filter(User.id == subscription.user_id).first()
                    if user:
                        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
                        
                        # Если пользователя нет в 3xUI, помечаем подписку как истекшую
                        if user_email not in active_emails:
                            subscription.status = "expired"
                            print(f"Подписка пользователя {user.telegram_id} помечена как истекшая (удалена из 3xUI)")
                        else:
                            # Если пользователь есть в 3xUI, проверяем дату истечения
                            # Находим клиента в 3xUI
                            client_info = None
                            for client in active_clients:
                                if client["email"] == user_email:
                                    client_info = client
                                    break
                            
                            if client_info:
                                # Проверяем, не истекла ли подписка по времени
                                current_time = datetime.utcnow()
                                if subscription.expires_at <= current_time:
                                    subscription.status = "expired"
                                    print(f"Подписка пользователя {user.telegram_id} помечена как истекшая (по времени)")
                
                db.commit()
                print(f"Синхронизация завершена. Активных клиентов в 3xUI: {len(active_clients)}")
            else:
                print(f"Ошибка синхронизации с 3xUI: {sync_result.get('msg', 'Неизвестная ошибка')}")
                
        except Exception as e:
            print(f"Ошибка при синхронизации с 3xUI: {e}")
    
    async def notify_referral_bonus(self, referrer_id: int, referred_user_name: str):
        """Уведомление о начислении реферального бонуса"""
        db = SessionLocal()
        try:
            referrer = db.query(User).filter(User.id == referrer_id).first()
            if referrer:
                message = (
                    f"🎉 Реферальный бонус!\n\n"
                    f"По вашей реферальной ссылке зарегистрировался пользователь: {referred_user_name}\n\n"
                    f"💰 Вам начислено: +{REFERRAL_BONUS} монет\n"
                    f"💎 Текущий баланс: {referrer.bonus_coins} монет\n\n"
                    f"💡 Напомним: {BONUS_TO_SUBSCRIPTION} монет = 1 месяц подписки\n"
                    f"Проверить баланс можно в разделе 'Реферальная система'"
                )
                
                try:
                    await self.bot.send_message(referrer.telegram_id, message)
                    print(f"Отправлено уведомление о реферальном бонусе пользователю {referrer.telegram_id}")
                except Exception as e:
                    print(f"Ошибка отправки уведомления о бонусе пользователю {referrer.telegram_id}: {e}")
                    
        except Exception as e:
            print(f"Ошибка при отправке уведомления о реферальном бонусе: {e}")
        finally:
            db.close()
    
    async def notify_subscription_purchased(self, user_id: int, plan: str, price: int):
        """Уведомление о покупке подписки"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                message = (
                    f"✅ Подписка успешно оплачена!\n\n"
                    f"Тариф: {plan}\n"
                    f"Сумма: {price}₽\n"
                    f"Дата покупки: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"Ваша конфигурация доступна в разделе 'Мои ключи'"
                )
                
                try:
                    await self.bot.send_message(user.telegram_id, message)
                    print(f"Отправлено уведомление о покупке подписки пользователю {user.telegram_id}")
                except Exception as e:
                    print(f"Ошибка отправки уведомления о покупке пользователю {user.telegram_id}: {e}")
                    
        except Exception as e:
            print(f"Ошибка при отправке уведомления о покупке: {e}")
        finally:
            db.close()

async def run_notification_scheduler(bot):
    """Запуск планировщика уведомлений"""
    notification_manager = NotificationManager(bot)
    
    while True:
        try:
            await notification_manager.check_expiring_subscriptions()
            print("Проверка истекающих подписок завершена")
        except Exception as e:
            print(f"Ошибка в планировщике уведомлений: {e}")
        
        # Проверяем каждые 6 часов
        await asyncio.sleep(6 * 60 * 60)
