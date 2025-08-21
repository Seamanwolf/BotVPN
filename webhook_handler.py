#!/usr/bin/env python3
"""
Webhook обработчик для входящих уведомлений от ЮKassa
"""

import asyncio
import json
import logging
import threading
import os
from datetime import datetime, timedelta
from typing import Dict, Any
from flask import Flask, request, jsonify
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

from database import SessionLocal, Payment, User, Subscription
from xui_client import XUIClient
from config import TARIFFS, CORPORATE_TARIFFS, REFERRAL_BONUS
from notifications import NotificationManager
import hmac
import hashlib
import base64

# Настройка логирования с более подробным выводом
logging.basicConfig(
    level=logging.DEBUG,  # Изменено с INFO на DEBUG
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Инициализация
app = Flask(__name__)
xui_client = XUIClient()
notification_manager = NotificationManager()

def safe_send_message(chat_id, text, parse_mode="HTML"):
    """
    Безопасная отправка сообщения с защитой от ошибок event loop
    Используем подход из oldwork.py
    """
    import os
    import sys
    import subprocess
    import json
    
    # Сохраняем сообщение во временный файл
    message_data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    # Создаем временный файл
    temp_file = f"/tmp/message_{chat_id}_{int(datetime.utcnow().timestamp())}.json"
    with open(temp_file, 'w') as f:
        json.dump(message_data, f)
    
    # Запускаем отдельный процесс для отправки сообщения
    try:
        # Создаем скрипт для отправки сообщения
        script_content = """#!/usr/bin/env python3
import json
import asyncio
import sys
import os
from dotenv import load_dotenv
from aiogram import Bot

# Загружаем переменные окружения
load_dotenv()

# Получаем токен бота из переменной окружения или из config.py
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    try:
        sys.path.append('/root')
        from config import BOT_TOKEN
        print(f"Using BOT_TOKEN from config.py: {BOT_TOKEN}")
    except ImportError:
        print("Error: BOT_TOKEN not found in environment or config.py")
        sys.exit(1)

# Создаем экземпляр бота
bot = Bot(token=BOT_TOKEN)

async def send_message_async(data_file):
    with open(data_file, 'r') as f:
        data = json.load(f)
    
    try:
        await bot.send_message(
            chat_id=data["chat_id"],
            text=data["text"],
            parse_mode=data.get("parse_mode", "HTML")
        )
        # Закрываем сессию бота
        await bot.session.close()
        return True
    except Exception as e:
        print(f"Error sending message: {e}")
        # Закрываем сессию бота даже в случае ошибки
        try:
            await bot.session.close()
        except:
            pass
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: script.py <data_file>")
        sys.exit(1)
        
    data_file = sys.argv[1]
    asyncio.run(send_message_async(data_file))
"""
        
        # Сохраняем скрипт во временный файл
        script_file = f"/tmp/send_message_{int(datetime.utcnow().timestamp())}.py"
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        # Делаем скрипт исполняемым
        os.chmod(script_file, 0o755)
        
        # Запускаем скрипт в фоновом режиме
        subprocess.Popen(
            [sys.executable, script_file, temp_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        logging.debug(f"Запущен фоновый процесс для отправки сообщения пользователю {chat_id}")
        return True
    except Exception as e:
        logging.error(f"Ошибка при запуске процесса отправки сообщения: {e}")
        return False

def verify_webhook_signature(request_body: bytes, signature: str) -> bool:
    """
    Проверка подписи webhook'а от ЮKassa
    В реальном проекте здесь должна быть проверка HMAC подписи
    """
    # TODO: Реализовать проверку подписи
    # Пока что просто возвращаем True для тестирования
    logging.debug(f"Webhook signature verification: {signature}")
    return True

def process_payment_webhook_sync(payment_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Синхронная обработка webhook'а от ЮKassa
    """
    try:
        logging.debug(f"=== НАЧАЛО ОБРАБОТКИ WEBHOOK ===")
        logging.debug(f"Полученные данные webhook: {json.dumps(payment_data, indent=2, ensure_ascii=False)}")
        
        payment_id = payment_data.get("object", {}).get("id")
        status = payment_data.get("object", {}).get("status")
        paid = payment_data.get("object", {}).get("paid", False)
        
        logging.debug(f"Извлеченные данные: payment_id={payment_id}, status={status}, paid={paid}")
        
        if not payment_id:
            logging.error("Webhook: отсутствует payment_id")
            return {"success": False, "error": "Missing payment_id"}
        
        logging.info(f"Webhook: получено уведомление для платежа {payment_id}, статус: {status}, оплачен: {paid}")
        
        # Дополнительная проверка статуса в YooKassa (как в oldwork.py)
        if status == "succeeded" and paid:
            try:
                # Проверяем статус в YooKassa еще раз для надежности
                from yookassa import Payment as YooKassaPayment, Configuration
                import os
                from dotenv import load_dotenv
                
                load_dotenv()
                # Используем переменные окружения или значения из config.py
                shop_id = os.getenv("YOOKASSA_SHOPID")
                secret_key = os.getenv("YOOKASSA_SECRET_KEY")
                
                if not shop_id or not secret_key:
                    from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
                    shop_id = YOOKASSA_SHOP_ID
                    secret_key = YOOKASSA_SECRET_KEY
                    
                Configuration.account_id = shop_id
                Configuration.secret_key = secret_key
                logging.debug(f"Настроены учетные данные YooKassa: account_id={shop_id}")
                
                if Configuration.account_id and Configuration.secret_key:
                    payment_check = YooKassaPayment.find_one(payment_id)
                    if payment_check.status != 'succeeded':
                        logging.warning(f"Webhook: статус в YooKassa ({payment_check.status}) не совпадает с webhook ({status})")
                        return {"success": False, "error": "Status mismatch"}
                    logging.info(f"Webhook: дополнительная проверка в YooKassa подтвердила статус {payment_check.status}")
                else:
                    logging.warning("Webhook: YooKassa API не настроен, пропускаем дополнительную проверку")
            except Exception as e:
                logging.error(f"Webhook: ошибка при дополнительной проверке статуса в YooKassa: {e}")
                # Продолжаем обработку, так как webhook уже подтвердил статус
        
        # Получаем платеж из БД
        db = SessionLocal()
        try:
            logging.debug(f"Поиск платежа {payment_id} в базе данных...")
            payment = db.query(Payment).filter(Payment.yookassa_payment_id == payment_id).first()
            if not payment:
                logging.error(f"Webhook: платеж {payment_id} не найден в БД")
                return {"success": False, "error": "Payment not found"}
            
            logging.debug(f"Платеж найден: ID={payment.id}, user_id={payment.user_id}, amount={payment.amount}, current_status={payment.status}, payment_type={payment.payment_type}")
            
            # Обновляем статус платежа
            old_status = payment.status
            payment.status = status
            logging.debug(f"Статус платежа изменен с '{old_status}' на '{status}'")
            
            if paid and status == "succeeded":
                logging.debug("Платеж оплачен и успешен, устанавливаем completed_at")
                payment.completed_at = datetime.utcnow()
                
                # Если платеж еще не обработан, создаем подписку или продлеваем
                if payment.status != "completed":
                    logging.debug("Платеж еще не обработан, проверяем тип платежа")
                    if payment.payment_type == "extension":
                        logging.debug("Это платеж для продления подписки")
                        logging.debug("Вызываем create_subscription_from_payment_sync для продления")
                        create_subscription_from_payment_sync(payment, db)
                    else:
                        logging.debug("Это платеж для новой подписки")
                        logging.debug("Вызываем create_subscription_from_payment_sync для новой подписки")
                        create_subscription_from_payment_sync(payment, db)
                else:
                    logging.debug("Платеж уже обработан, пропускаем создание подписки")
            else:
                logging.debug(f"Платеж не подходит для обработки: paid={paid}, status={status}")
                    
            db.commit()
            logging.debug("Изменения сохранены в базе данных")
            
            logging.info(f"Webhook: платеж {payment_id} обновлен, статус: {status}")
            return {"success": True, "message": "Payment updated"}
            
        finally:
            db.close()
            logging.debug("Соединение с базой данных закрыто")
            
    except Exception as e:
        logging.error(f"Webhook: ошибка обработки платежа: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def create_subscription_from_payment_sync(payment: Payment, db: Session):
    """
    Синхронное создание подписки из оплаченного платежа
    """
    try:
        logging.debug(f"=== НАЧАЛО СОЗДАНИЯ ПОДПИСКИ ===")
        logging.debug(f"Платеж: ID={payment.id}, user_id={payment.user_id}, subscription_type={payment.subscription_type}, payment_type={payment.payment_type}")
        
        # Получаем пользователя
        logging.debug(f"Поиск пользователя {payment.user_id} в базе данных...")
        user = db.query(User).filter(User.id == payment.user_id).first()
        if not user:
            logging.error(f"Webhook: пользователь {payment.user_id} не найден")
            return
        
        logging.debug(f"Пользователь найден: telegram_id={user.telegram_id}, full_name={user.full_name}")
        
        # Проверяем тип платежа
        if payment.payment_type == "extension":
            # Это продление подписки
            logging.debug("Обработка продления подписки")
            extend_subscription_from_payment_sync(payment, db, user)
        else:
            # Это новая подписка
            logging.debug("Обработка новой подписки")
            create_new_subscription_from_payment_sync(payment, db, user)
            
    except Exception as e:
        logging.error(f"Webhook: ошибка создания подписки: {e}", exc_info=True)

def create_new_subscription_from_payment_sync(payment: Payment, db: Session, user: User):
    """
    Создание новой подписки из оплаченного платежа
    """
    try:
        # Проверяем, не был ли уже обработан этот платеж (как в oldwork.py)
        if payment.status == "completed":
            logging.info(f"Webhook: платеж {payment.yookassa_payment_id} уже обработан, пропускаем создание подписки")
            return
        # Определяем параметры подписки
        tariff = payment.subscription_type
        key_type = "personal"  # по умолчанию личный ключ
        users_count = 3  # по умолчанию для личных тарифов
        logging.debug(f"Определение параметров тарифа: {tariff}")
        
        if tariff == "1m":
            days = TARIFFS["1m"]["days"]
            tariff_name = TARIFFS["1m"]["name"]
        elif tariff == "3m":
            days = TARIFFS["3m"]["days"]
            tariff_name = TARIFFS["3m"]["name"]
        elif tariff == "test":
            days = TARIFFS["test"]["days"]
            tariff_name = TARIFFS["test"]["name"]
        elif tariff == "corporate_test":
            # Тестовый корпоративный тариф
            days = 1
            tariff_name = "1 день, 5 пользователей"
            key_type = "corporate"
            users_count = 5
        elif tariff.startswith("corporate_"):
            # Корпоративный тариф
            corporate_tariff_type = tariff.split("_")[1]  # 1m или 3m
            days = CORPORATE_TARIFFS[corporate_tariff_type]["days"]
            tariff_name = CORPORATE_TARIFFS[corporate_tariff_type]["name"]
            key_type = "corporate"
            
            # Получаем количество пользователей из метаданных
            if payment.payment_metadata:
                try:
                    metadata = json.loads(payment.payment_metadata)
                    users_count = metadata.get("users_count", 5)
                    tariff_name += f" ({users_count} пользователей)"
                except:
                    users_count = 5
                    tariff_name += " (5 пользователей)"
            else:
                users_count = 5
                tariff_name += " (5 пользователей)"
        else:
            logging.error(f"Webhook: неизвестный тариф {tariff}")
            return
        
        logging.debug(f"Параметры тарифа: days={days}, tariff_name={tariff_name}")
        
        # Создаем подписку в 3xUI
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        logging.debug(f"Email для 3xUI: {user_email}")
        
        # Определяем следующий номер подписки
        existing_subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
        next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
        logging.debug(f"Следующий номер подписки: {next_subscription_number}")
        
        logging.debug("Вызов XUI клиента для создания пользователя...")
        # Создаем один event loop для всех асинхронных операций
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Определяем лимит IP для корпоративных тарифов
            ip_limit = 3  # по умолчанию для личных тарифов
            if key_type == "corporate":
                ip_limit = users_count  # для корпоративных тарифов лимит = количество пользователей
            
            xui_result = loop.run_until_complete(xui_client.create_user(
                user_email, 
                days, 
                f"{user.full_name} (PAID)", 
                str(user.telegram_id), 
                next_subscription_number,
                ip_limit=ip_limit
            ))
            
            logging.debug(f"Результат создания пользователя в XUI: {xui_result}")
            
            if xui_result:
                logging.debug("Пользователь создан в XUI, получаем конфигурацию...")
                config = loop.run_until_complete(xui_client.get_user_config(xui_result["email"], next_subscription_number))
                logging.debug(f"Полученная конфигурация: {config}")
                
                if config:
                    # Создаем подписку в БД
                    expires_at = datetime.utcnow() + timedelta(days=days)
                    logging.debug(f"Дата истечения подписки: {expires_at}")
                    
                    subscription = Subscription(
                        user_id=user.id,
                        plan=tariff,
                        plan_name=tariff_name,
                        status="active",
                        subscription_number=next_subscription_number,
                        key_type=key_type,
                        expires_at=expires_at
                    )
                    db.add(subscription)
                    logging.debug("Подписка добавлена в сессию БД")
                    
                    # Обновляем статус платежа
                    payment.status = "completed"
                    payment.completed_at = datetime.utcnow()
                    logging.debug("Статус платежа обновлен на 'completed'")
                    
                    db.commit()
                    logging.debug("Подписка и платеж сохранены в БД")
                    
                    # Отправляем уведомление пользователю
                    logging.debug("Подготовка сообщения об успешной оплате...")
                    apps_text = "\n📱 <b>Рекомендуемые приложения:</b>\n\n"
                    apps_text += "<b>Android:</b>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
                    apps_text += "<b>iPhone:</b>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
                    apps_text += "<b>Windows:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://github.com/2dust/v2rayN/releases\">V2rayN</a>\n\n"
                    apps_text += "<b>Mac:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">FoxRay</a>\n"
                    apps_text += "• <a href=\"https://github.com/yichengchen/clashX/releases\">ClashX</a>\n\n"
                    
                    success_message = f"✅ <b>Оплата прошла успешно!</b>\n\n"
                    success_message += f"📋 <b>Тариф:</b> {tariff_name}\n"
                    success_message += f"💰 <b>Сумма:</b> {payment.amount}₽\n"
                    success_message += f"⏰ <b>Действует до:</b> {expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                    success_message += f"🔗 <b>Конфигурация:</b>\n"
                    if isinstance(config, dict) and 'subscription_url' in config:
                        success_message += f"<code>{config['subscription_url']}</code>\n\n"
                    else:
                        success_message += f"<code>{config}</code>\n\n"
                    success_message += apps_text
                    success_message += "\n📋 <b>Инструкция по подключению:</b>\n"
                    success_message += "1. Скачайте приложение для вашей платформы\n"
                    success_message += "2. Скопируйте подписочную ссылку из раздела '🔑 Мои ключи'\n"
                    success_message += "3. Вставьте ссылку в приложение\n"
                    success_message += "4. Нажмите 'Подключить'\n\n"
                    success_message += "Если у вас есть вопросы, не стесняйтесь обращаться!"
                    
                    logging.debug(f"Отправка сообщения пользователю {user.telegram_id}...")
                    # Отправляем сообщение пользователю через бота
                    safe_send_message(user.telegram_id, success_message)
                    
                    # Начисляем реферальный бонус только при первой покупке
                    if user.referred_by and not user.has_made_first_purchase:
                        logging.debug(f"Начисление реферального бонуса для пользователя {user.referred_by}")
                        referrer = db.query(User).filter(User.id == user.referred_by).first()
                        if referrer:
                            referrer.bonus_coins += REFERRAL_BONUS
                            user.has_made_first_purchase = True
                            db.merge(referrer)
                            db.merge(user)
                            db.commit()
                            logging.debug(f"Реферальный бонус начислен: {REFERRAL_BONUS} монет")
                            
                            # Отправляем уведомление о реферальном бонусе
                            try:
                                new_loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(new_loop)
                                new_loop.run_until_complete(notification_manager.notify_referral_bonus(referrer.telegram_id, user.full_name))
                                logging.debug("Уведомление о реферальном бонусе отправлено")
                            except Exception as e:
                                logging.error(f"Webhook: ошибка при отправке реферального уведомления: {e}")
                                # Если произошла ошибка с event loop, создаем новый
                                if "Event loop is closed" in str(e):
                                    logging.debug("Создаем новый event loop после ошибки отправки реферального уведомления")
                                    try:
                                        new_loop.close()
                                    except:
                                        pass
                                    new_loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(new_loop)
                                    try:
                                        new_loop.run_until_complete(notification_manager.notify_referral_bonus(referrer.telegram_id, user.full_name))
                                        logging.debug("Повторная отправка реферального уведомления успешна")
                                    except Exception as e2:
                                        logging.error(f"Webhook: повторная ошибка при отправке реферального уведомления: {e2}")
                            finally:
                                if 'new_loop' in locals():
                                    try:
                                        new_loop.close()
                                    except:
                                        pass
                    
                    logging.info(f"Webhook: подписка создана для пользователя {user.telegram_id}")
                    
                    # Отправляем уведомление администраторам о новой покупке
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        new_loop.run_until_complete(notification_manager.notify_admin_new_purchase(user, subscription, payment.amount))
                        logging.debug("Уведомление администраторам о новой покупке отправлено")
                    except Exception as e:
                        logging.error(f"Webhook: ошибка при отправке уведомления администраторам: {e}")
                        # Если произошла ошибка с event loop, создаем новый
                        if "Event loop is closed" in str(e):
                            logging.debug("Создаем новый event loop после ошибки отправки уведомления о покупке")
                            try:
                                new_loop.close()
                            except:
                                pass
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                new_loop.run_until_complete(notification_manager.notify_admin_new_purchase(user, subscription, payment.amount))
                                logging.debug("Повторная отправка уведомления о покупке успешна")
                            except Exception as e2:
                                logging.error(f"Webhook: повторная ошибка при отправке уведомления о покупке: {e2}")
                    finally:
                        if 'new_loop' in locals():
                            try:
                                new_loop.close()
                            except:
                                pass
                    
                    logging.debug("=== СОЗДАНИЕ ПОДПИСКИ ЗАВЕРШЕНО УСПЕШНО ===")
                else:
                    logging.error(f"Webhook: ошибка получения конфигурации для пользователя {user.telegram_id}")
            else:
                logging.error(f"Webhook: ошибка создания пользователя в 3xUI для {user.telegram_id}")
        finally:
            try:
                loop.close()
            except:
                pass
            
    except Exception as e:
        logging.error(f"Webhook: ошибка создания новой подписки: {e}", exc_info=True)

def extend_subscription_from_payment_sync(payment: Payment, db: Session, user: User):
    """
    Продление подписки из оплаченного платежа
    """
    try:
        logging.debug(f"=== НАЧАЛО ПРОДЛЕНИЯ ПОДПИСКИ ===")
        logging.debug(f"Платеж: ID={payment.id}, user_id={payment.user_id}, subscription_type={payment.subscription_type}, payment_type={payment.payment_type}, status={payment.status}")
        
        # Проверяем, не был ли уже обработан этот платеж (как в oldwork.py)
        if payment.status == "completed":
            logging.info(f"Webhook: платеж {payment.yookassa_payment_id} уже обработан, пропускаем продление")
            return
        
        # Получаем подписку из метаданных платежа
        subscription_id = None
        logging.debug(f"Метаданные платежа: {payment.payment_metadata}")
        
        if payment.payment_metadata:
            try:
                metadata = json.loads(payment.payment_metadata)
                logging.debug(f"Распарсенные метаданные: {metadata}")
                if 'subscription_id' in metadata:
                    subscription_id = metadata['subscription_id']
                    logging.debug(f"Найден subscription_id в метаданных: {subscription_id}")
                else:
                    logging.error(f"Webhook: ключ subscription_id не найден в метаданных: {metadata}")
            except json.JSONDecodeError as e:
                logging.error(f"Webhook: ошибка парсинга payment_metadata: {e}")
                logging.error(f"Содержимое метаданных: {payment.payment_metadata}")
                return
        else:
            logging.error("Webhook: payment_metadata отсутствует")
        
        if not subscription_id:
            logging.error("Webhook: subscription_id не найден в метаданных платежа")
            return
        
        logging.debug(f"ID подписки для продления: {subscription_id}")
        
        # Получаем подписку
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id, Subscription.user_id == user.id).first()
        if not subscription:
            logging.error(f"Webhook: подписка {subscription_id} не найдена")
            return
        
        logging.debug(f"Подписка найдена: ID={subscription.id}, статус={subscription.status}, истекает={subscription.expires_at}")
        
        # Определяем параметры продления
        tariff = payment.subscription_type
        logging.debug(f"Определение параметров тарифа: {tariff}")
        
        if tariff == "test":
            days = TARIFFS["test"]["days"]
            tariff_name = TARIFFS["test"]["name"]
        elif tariff == "1m":
            days = TARIFFS["1m"]["days"]
            tariff_name = TARIFFS["1m"]["name"]
        elif tariff == "3m":
            days = TARIFFS["3m"]["days"]
            tariff_name = TARIFFS["3m"]["name"]
        else:
            logging.error(f"Webhook: неизвестный тариф для продления {tariff}")
            return
        
        logging.debug(f"Параметры продления: days={days}, tariff_name={tariff_name}")
        
        # Продлеваем подписку в 3xUI
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        logging.debug(f"Email для 3xUI: {user_email}")
        
        # Создаем один event loop для всех асинхронных операций
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Формируем уникальный email для поиска пользователя в 3xUI
            unique_email = f"SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number}"
            logging.debug(f"Уникальный email для поиска: {unique_email}")
            
            # Если подписка истекла, создаем нового пользователя
            if subscription.status == "expired":
                logging.debug("Подписка истекла, создаем нового пользователя")
                # Определяем лимит IP для корпоративных тарифов
                ip_limit = 3  # по умолчанию для личных тарифов
                if subscription.key_type == "corporate":
                    # Для корпоративных тарифов определяем количество пользователей из названия плана
                    if "5 пользователей" in subscription.plan_name:
                        ip_limit = 5
                    elif "10 пользователей" in subscription.plan_name:
                        ip_limit = 10
                    elif "15 пользователей" in subscription.plan_name:
                        ip_limit = 15
                    elif "20 пользователей" in subscription.plan_name:
                        ip_limit = 20
                    else:
                        ip_limit = 5  # по умолчанию для корпоративных
                
                xui_result = loop.run_until_complete(xui_client.create_user(
                    user_email, 
                    days, 
                    f"{user.full_name} (EXTENDED)", 
                    str(user.telegram_id),
                    subscription.subscription_number,
                    ip_limit=ip_limit
                ))
            else:
                # Если подписка еще активна, продлеваем существующего пользователя
                logging.debug("Подписка активна, продлеваем существующего пользователя")
                
                # Продлеваем существующего пользователя
                try:
                    xui_result = loop.run_until_complete(xui_client.extend_user(
                        unique_email,
                        days
                    ))
                except Exception as e:
                    logging.error(f"Webhook: ошибка при продлении в 3xUI: {e}")
                    xui_result = None
                    # Если произошла ошибка с event loop, создаем новый
                    if "Event loop is closed" in str(e):
                        logging.debug("Создаем новый event loop после ошибки")
                        try:
                            loop.close()
                        except:
                            pass
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            xui_result = loop.run_until_complete(xui_client.extend_user(
                                unique_email,
                                days
                            ))
                            logging.debug("Повторная попытка продления успешна")
                        except Exception as e2:
                            logging.error(f"Webhook: повторная ошибка при продлении в 3xUI: {e2}")
                            xui_result = None
            
            logging.debug(f"Результат продления в XUI: {xui_result}")
            
            if xui_result:
                # Получаем новую конфигурацию
                try:
                    config = loop.run_until_complete(xui_client.get_user_config(xui_result["email"], subscription.subscription_number))
                except Exception as e:
                    logging.error(f"Webhook: ошибка при получении конфигурации: {e}")
                    config = None
                logging.debug(f"Полученная конфигурация: {config}")
                
                if config:
                    # Обновляем подписку в БД
                    if subscription.status == "expired":
                        subscription.expires_at = datetime.utcnow() + timedelta(days=days)
                        logging.debug(f"Подписка восстановлена, новая дата истечения: {subscription.expires_at}")
                    else:
                        subscription.expires_at = subscription.expires_at + timedelta(days=days)
                        logging.debug(f"Подписка продлена, новая дата истечения: {subscription.expires_at}")
                    
                    # Обновляем поля продлений
                    subscription.extensions_count += 1
                    subscription.last_extension_date = datetime.utcnow()
                    subscription.total_days_added += days
                    subscription.status = "active"
                    logging.debug("Статус подписки обновлен на 'active'")
                    logging.debug(f"Продлений: {subscription.extensions_count}, добавлено дней: {subscription.total_days_added}")
                    
                    # Обновляем статус платежа
                    payment.status = "completed"
                    payment.completed_at = datetime.utcnow()
                    logging.debug("Статус платежа обновлен на 'completed'")
                    
                    db.commit()
                    logging.debug("Подписка и платеж сохранены в БД")
                    
                    # Отправляем уведомление пользователю
                    logging.debug("Подготовка сообщения об успешном продлении...")
                    apps_text = "\n📱 <b>Рекомендуемые приложения:</b>\n\n"
                    apps_text += "<b>Android:</b>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a>\n"
                    apps_text += "• <a href=\"https://play.google.com/store/apps/details?id=com.github.kr328.clash\">Clash for Android</a>\n\n"
                    apps_text += "<b>iPhone:</b>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/streisand/id6450534064\">Streisand</a>\n"
                    apps_text += "• <a href=\"https://apps.apple.com/app/shadowrocket/id932747118\">Shadowrocket</a>\n\n"
                    apps_text += "<b>Windows:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">Hiddify</a>\n"
                    apps_text += "• <a href=\"https://github.com/2dust/v2rayN/releases\">V2rayN</a>\n\n"
                    apps_text += "<b>Mac:</b>\n"
                    apps_text += "• <a href=\"https://github.com/hiddify/hiddify-next/releases\">FoxRay</a>\n"
                    apps_text += "• <a href=\"https://github.com/yichengchen/clashX/releases\">ClashX</a>\n\n"
                    
                    success_message = f"✅ <b>Подписка успешно продлена!</b>\n\n"
                    success_message += f"📋 <b>Тариф:</b> {tariff_name}\n"
                    success_message += f"💰 <b>Сумма:</b> {payment.amount}₽\n"
                    success_message += f"⏰ <b>Дополнительно дней:</b> {days}\n"
                    success_message += f"📅 <b>Новая дата окончания:</b> {subscription.expires_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                    success_message += f"🔗 <b>Конфигурация:</b>\n"
                    if isinstance(config, dict) and 'subscription_url' in config:
                        success_message += f"<code>{config['subscription_url']}</code>\n\n"
                    else:
                        success_message += f"<code>{config}</code>\n\n"
                    success_message += apps_text
                    success_message += "\n📋 <b>Инструкция по подключению:</b>\n"
                    success_message += "1. Скачайте приложение для вашей платформы\n"
                    success_message += "2. Скопируйте подписочную ссылку из раздела '🔑 Мои ключи'\n"
                    success_message += "3. Вставьте ссылку в приложение\n"
                    success_message += "4. Нажмите 'Подключить'\n\n"
                    success_message += "Если у вас есть вопросы, не стесняйтесь обращаться!"
                    
                    logging.debug(f"Отправка сообщения пользователю {user.telegram_id}...")
                    # Отправляем сообщение пользователю через бота
                    safe_send_message(user.telegram_id, success_message)
                    
                    logging.info(f"Webhook: подписка продлена для пользователя {user.telegram_id}")
                    
                    # Отправляем уведомление администраторам о продлении
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        new_loop.run_until_complete(notification_manager.notify_admin_extension(user, subscription, payment.amount, days))
                        logging.debug("Уведомление администраторам о продлении отправлено")
                    except Exception as e:
                        logging.error(f"Webhook: ошибка при отправке уведомления администраторам о продлении: {e}")
                        # Если произошла ошибка с event loop, создаем новый
                        if "Event loop is closed" in str(e):
                            logging.debug("Создаем новый event loop после ошибки отправки уведомления о продлении")
                            try:
                                new_loop.close()
                            except:
                                pass
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                new_loop.run_until_complete(notification_manager.notify_admin_extension(user, subscription, payment.amount, days))
                                logging.debug("Повторная отправка уведомления о продлении успешна")
                            except Exception as e2:
                                logging.error(f"Webhook: повторная ошибка при отправке уведомления о продлении: {e2}")
                    finally:
                        if 'new_loop' in locals():
                            try:
                                new_loop.close()
                            except:
                                pass
                    
                    logging.debug("=== ПРОДЛЕНИЕ ПОДПИСКИ ЗАВЕРШЕНО УСПЕШНО ===")
                else:
                    logging.error(f"Webhook: ошибка получения конфигурации для продления пользователя {user.telegram_id}")
            else:
                logging.error(f"Webhook: ошибка продления пользователя в 3xUI для {user.telegram_id}")
        finally:
            # Не закрываем event loop здесь, чтобы избежать ошибок "Event loop is closed"
            # Он будет закрыт автоматически при завершении процесса
            pass
            
    except Exception as e:
        logging.error(f"Webhook: ошибка продления подписки: {e}", exc_info=True)

@app.route('/webhook/yookassa', methods=['POST'])
def yookassa_webhook():
    """
    Webhook endpoint для ЮKassa
    """
    try:
        logging.debug(f"=== ПОЛУЧЕН WEBHOOK ЗАПРОС ===")
        logging.debug(f"Headers: {dict(request.headers)}")
        logging.debug(f"Method: {request.method}")
        logging.debug(f"URL: {request.url}")
        
        # Получаем данные webhook'а
        webhook_data = request.get_json()
        logging.debug(f"Raw webhook data: {webhook_data}")
        
        if not webhook_data:
            logging.error("Webhook: пустые данные")
            return jsonify({"error": "Empty data"}), 400
        
        # Проверяем подпись (в реальном проекте)
        signature = request.headers.get('X-YooKassa-Signature')
        logging.debug(f"Signature from headers: {signature}")
        
        if not verify_webhook_signature(request.data, signature):
            logging.error("Webhook: неверная подпись")
            return jsonify({"error": "Invalid signature"}), 401
        
        # Обрабатываем webhook в отдельном потоке
        logging.debug("Запуск обработки webhook'а в отдельном потоке...")
        thread = threading.Thread(target=process_payment_webhook_sync, args=(webhook_data,))
        thread.daemon = True
        thread.start()
        
        logging.info("Webhook: уведомление получено и обрабатывается")
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logging.error(f"Webhook: ошибка обработки: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/health', methods=['GET'])
def health_check():
    """
    Проверка здоровья webhook сервера
    """
    logging.debug("Health check request received")
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

if __name__ == "__main__":
    # Запускаем webhook сервер
    logging.info("Запуск webhook сервера на порту 5001...")
    app.run(host='0.0.0.0', port=5001, debug=False)
