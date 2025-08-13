#!/usr/bin/env python3
"""
Webhook обработчик для входящих уведомлений от ЮKassa
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from flask import Flask, request, jsonify
from sqlalchemy.orm import Session

from database import SessionLocal, Payment, User, Subscription
from xui_client import XUIClient
from config import TARIFFS, REFERRAL_BONUS
from notifications import NotificationManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
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
    return True

async def process_payment_webhook(payment_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработка webhook'а от ЮKassa
    """
    try:
        payment_id = payment_data.get("object", {}).get("id")
        status = payment_data.get("object", {}).get("status")
        paid = payment_data.get("object", {}).get("paid", False)
        
        if not payment_id:
            logging.error("Webhook: отсутствует payment_id")
            return {"success": False, "error": "Missing payment_id"}
        
        logging.info(f"Webhook: получено уведомление для платежа {payment_id}, статус: {status}, оплачен: {paid}")
        
        # Получаем платеж из БД
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(Payment.yookassa_payment_id == payment_id).first()
            if not payment:
                logging.error(f"Webhook: платеж {payment_id} не найден в БД")
                return {"success": False, "error": "Payment not found"}
            
            # Обновляем статус платежа
            payment.status = status
            if paid and status == "succeeded":
                payment.completed_at = datetime.utcnow()
                
                # Если платеж еще не обработан, создаем подписку
                if payment.status != "completed":
                    await create_subscription_from_payment(payment, db)
                    
            db.commit()
            
            logging.info(f"Webhook: платеж {payment_id} обновлен, статус: {status}")
            return {"success": True, "message": "Payment updated"}
            
        finally:
            db.close()
            
    except Exception as e:
        logging.error(f"Webhook: ошибка обработки платежа: {e}")
        return {"success": False, "error": str(e)}

async def create_subscription_from_payment(payment: Payment, db: Session):
    """
    Создание подписки из оплаченного платежа
    """
    try:
        # Получаем пользователя
        user = db.query(User).filter(User.id == payment.user_id).first()
        if not user:
            logging.error(f"Webhook: пользователь {payment.user_id} не найден")
            return
        
        # Определяем параметры подписки
        tariff = payment.subscription_type
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
        
        # Создаем подписку в 3xUI
        user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
        
        # Определяем следующий номер подписки
        existing_subscriptions = db.query(Subscription).filter(Subscription.user_id == user.id).all()
        next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
        
        xui_result = await xui_client.create_user(
            user_email, 
            days, 
            f"{user.full_name} (PAID)", 
            str(user.telegram_id), 
            next_subscription_number
        )
        
        if xui_result:
            config = await xui_client.get_user_config(xui_result["email"], next_subscription_number)
            
            if config:
                # Создаем подписку в БД
                expires_at = datetime.utcnow() + timedelta(days=days)
                
                subscription = Subscription(
                    user_id=user.id,
                    plan=tariff,
                    plan_name=tariff_name,
                    status="active",
                    subscription_number=next_subscription_number,
                    expires_at=expires_at
                )
                db.add(subscription)
                
                # Обновляем статус платежа
                payment.status = "completed"
                payment.completed_at = datetime.utcnow()
                
                db.commit()
                
                # Отправляем уведомление пользователю
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
                
                # Отправляем сообщение пользователю через бота
                from bot import bot
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=success_message,
                    parse_mode="HTML"
                )
                
                # Начисляем реферальный бонус только при первой покупке
                if user.referred_by and not user.has_made_first_purchase:
                    referrer = db.query(User).filter(User.id == user.referred_by).first()
                    if referrer:
                        referrer.bonus_coins += REFERRAL_BONUS
                        user.has_made_first_purchase = True
                        db.merge(referrer)
                        db.merge(user)
                        db.commit()
                        
                        # Отправляем уведомление о реферальном бонусе
                        await notification_manager.notify_referral_bonus(referrer.telegram_id, user.full_name)
                
                logging.info(f"Webhook: подписка создана для пользователя {user.telegram_id}")
            else:
                logging.error(f"Webhook: ошибка получения конфигурации для пользователя {user.telegram_id}")
        else:
            logging.error(f"Webhook: ошибка создания пользователя в 3xUI для {user.telegram_id}")
            
    except Exception as e:
        logging.error(f"Webhook: ошибка создания подписки: {e}")

@app.route('/webhook/yookassa', methods=['POST'])
def yookassa_webhook():
    """
    Webhook endpoint для ЮKassa
    """
    try:
        # Получаем данные webhook'а
        webhook_data = request.get_json()
        
        if not webhook_data:
            logging.error("Webhook: пустые данные")
            return jsonify({"error": "Empty data"}), 400
        
        # Проверяем подпись (в реальном проекте)
        signature = request.headers.get('X-YooKassa-Signature')
        if not verify_webhook_signature(request.data, signature):
            logging.error("Webhook: неверная подпись")
            return jsonify({"error": "Invalid signature"}), 401
        
        # Обрабатываем webhook асинхронно
        asyncio.create_task(process_payment_webhook(webhook_data))
        
        logging.info("Webhook: уведомление получено и обрабатывается")
        return jsonify({"success": True}), 200
        
    except Exception as e:
        logging.error(f"Webhook: ошибка обработки: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/health', methods=['GET'])
def health_check():
    """
    Проверка здоровья webhook сервера
    """
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

if __name__ == "__main__":
    # Запускаем webhook сервер
    app.run(host='0.0.0.0', port=5001, debug=False)
