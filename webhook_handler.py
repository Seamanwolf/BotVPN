#!/usr/bin/env python3
"""
Webhook обработчик для входящих уведомлений от ЮKassa
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any
from flask import Flask, request, jsonify
from sqlalchemy.orm import Session

from database import SessionLocal, Payment, User, Subscription
from xui_client import XUIClient
from config import TARIFFS, REFERRAL_BONUS
from notifications import NotificationManager

# Настройка логирования с более подробным выводом
logging.basicConfig(
    level=logging.DEBUG,  # Изменено с INFO на DEBUG
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

app = Flask(__name__)
xui_client = XUIClient()
notification_manager = NotificationManager()

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
                        create_subscription_from_payment_sync(payment, db)
                    else:
                        logging.debug("Это платеж для новой подписки")
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
        # Определяем параметры подписки
        tariff = payment.subscription_type
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
            xui_result = loop.run_until_complete(xui_client.create_user(
                user_email, 
                days, 
                f"{user.full_name} (PAID)", 
                str(user.telegram_id), 
                next_subscription_number
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
                    
                    logging.debug(f"Отправка сообщения пользователю {user.telegram_id}...")
                    # Отправляем сообщение пользователю через бота
                    from bot import bot
                    loop.run_until_complete(bot.send_message(
                        chat_id=user.telegram_id,
                        text=success_message,
                        parse_mode="HTML"
                    ))
                    logging.debug("Сообщение отправлено пользователю")
                    
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
                            loop.run_until_complete(notification_manager.notify_referral_bonus(referrer.telegram_id, user.full_name))
                            logging.debug("Уведомление о реферальном бонусе отправлено")
                    
                    logging.info(f"Webhook: подписка создана для пользователя {user.telegram_id}")
                    logging.debug("=== СОЗДАНИЕ ПОДПИСКИ ЗАВЕРШЕНО УСПЕШНО ===")
                else:
                    logging.error(f"Webhook: ошибка получения конфигурации для пользователя {user.telegram_id}")
            else:
                logging.error(f"Webhook: ошибка создания пользователя в 3xUI для {user.telegram_id}")
        finally:
            loop.close()
            
    except Exception as e:
        logging.error(f"Webhook: ошибка создания новой подписки: {e}", exc_info=True)

def extend_subscription_from_payment_sync(payment: Payment, db: Session, user: User):
    """
    Продление подписки из оплаченного платежа
    """
    try:
        logging.debug(f"=== НАЧАЛО ПРОДЛЕНИЯ ПОДПИСКИ ===")
        
        # Получаем подписку из метаданных платежа
        subscription_id = None
        if payment.payment_metadata:
            try:
                metadata = json.loads(payment.payment_metadata)
                if 'subscription_id' in metadata:
                    subscription_id = metadata['subscription_id']
            except json.JSONDecodeError:
                logging.error("Webhook: ошибка парсинга payment_metadata")
                return
        
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Если подписка истекла, создаем нового пользователя
            if subscription.status == "expired":
                logging.debug("Подписка истекла, создаем нового пользователя")
                xui_result = loop.run_until_complete(xui_client.create_user(
                    user_email, 
                    days, 
                    f"{user.full_name} (EXTENDED)", 
                    str(user.telegram_id),
                    subscription.subscription_number
                ))
            else:
                # Если подписка еще активна, добавляем дни к существующему
                logging.debug("Подписка активна, добавляем дни")
                xui_result = loop.run_until_complete(xui_client.create_user(
                    user_email, 
                    days, 
                    f"{user.full_name} (EXTENDED)", 
                    str(user.telegram_id),
                    subscription.subscription_number
                ))
            
            logging.debug(f"Результат продления в XUI: {xui_result}")
            
            if xui_result:
                # Получаем новую конфигурацию
                config = loop.run_until_complete(xui_client.get_user_config(xui_result["email"], subscription.subscription_number))
                logging.debug(f"Полученная конфигурация: {config}")
                
                if config:
                    # Обновляем подписку в БД
                    if subscription.status == "expired":
                        subscription.expires_at = datetime.utcnow() + timedelta(days=days)
                        logging.debug(f"Подписка восстановлена, новая дата истечения: {subscription.expires_at}")
                    else:
                        subscription.expires_at = subscription.expires_at + timedelta(days=days)
                        logging.debug(f"Подписка продлена, новая дата истечения: {subscription.expires_at}")
                    
                    subscription.status = "active"
                    logging.debug("Статус подписки обновлен на 'active'")
                    
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
                    
                    logging.debug(f"Отправка сообщения пользователю {user.telegram_id}...")
                    # Отправляем сообщение пользователю через бота
                    from bot import bot
                    loop.run_until_complete(bot.send_message(
                        chat_id=user.telegram_id,
                        text=success_message,
                        parse_mode="HTML"
                    ))
                    logging.debug("Сообщение отправлено пользователю")
                    
                    logging.info(f"Webhook: подписка продлена для пользователя {user.telegram_id}")
                    logging.debug("=== ПРОДЛЕНИЕ ПОДПИСКИ ЗАВЕРШЕНО УСПЕШНО ===")
                else:
                    logging.error(f"Webhook: ошибка получения конфигурации для продления пользователя {user.telegram_id}")
            else:
                logging.error(f"Webhook: ошибка продления пользователя в 3xUI для {user.telegram_id}")
        finally:
            loop.close()
            
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
