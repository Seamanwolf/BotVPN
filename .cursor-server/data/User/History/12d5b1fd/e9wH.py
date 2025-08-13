#!/usr/bin/env python3
"""
Модуль для отправки уведомлений пользователям
"""

import asyncio
from datetime import datetime, timedelta
from typing import List
from database import SessionLocal, User, Subscription
from config import REFERRAL_BONUS, BONUS_TO_SUBSCRIPTION

class NotificationManager:
    def __init__(self, bot):
        self.bot = bot
    
    async def check_expiring_subscriptions(self):
        """Проверка подписок, которые скоро истекают"""
        db = SessionLocal()
        try:
            # Подписки, которые истекают через 3 дня
            three_days_from_now = datetime.utcnow() + timedelta(days=3)
            expiring_soon = db.query(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at <= three_days_from_now,
                Subscription.expires_at > datetime.utcnow()
            ).all()
            
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
                            f"Чтобы продолжить пользоваться VPN, продлите подписку в разделе 'Купить ключ'"
                        )
                    else:
                        # Истекает через несколько дней
                        message = (
                            f"⚠️ Напоминание! Ваша подписка истекает через {days_left} дней\n\n"
                            f"Тариф: {subscription.plan}\n"
                            f"Дата истечения: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
                            f"Чтобы не потерять доступ к VPN, продлите подписку заранее"
                        )
                    
                    try:
                        await self.bot.send_message(user.telegram_id, message)
                        print(f"Отправлено уведомление об истечении подписки пользователю {user.telegram_id}")
                    except Exception as e:
                        print(f"Ошибка отправки уведомления пользователю {user.telegram_id}: {e}")
            
            # Подписки, которые уже истекли
            expired = db.query(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at <= datetime.utcnow()
            ).all()
            
            for subscription in expired:
                # Обновляем статус подписки
                subscription.status = "expired"
                
                user = db.query(User).filter(User.id == subscription.user_id).first()
                if user:
                    message = (
                        f"❌ Ваша подписка истекла!\n\n"
                        f"Тариф: {subscription.plan}\n"
                        f"Дата истечения: {subscription.expires_at.strftime('%d.%m.%Y')}\n\n"
                        f"Для восстановления доступа к VPN продлите подписку в разделе 'Купить ключ'"
                    )
                    
                    try:
                        await self.bot.send_message(user.telegram_id, message)
                        print(f"Отправлено уведомление об истечении подписки пользователю {user.telegram_id}")
                    except Exception as e:
                        print(f"Ошибка отправки уведомления пользователю {user.telegram_id}: {e}")
            
            db.commit()
            
        except Exception as e:
            print(f"Ошибка при проверке истекающих подписок: {e}")
            db.rollback()
        finally:
            db.close()
    
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
