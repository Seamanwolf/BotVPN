import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from yookassa import Payment, Configuration
from config import YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class YooKassaClient:
    def __init__(self):
        # Настраиваем SDK ЮKassa
        Configuration.account_id = YOOKASSA_SHOP_ID
        Configuration.secret_key = YOOKASSA_SECRET_KEY
        
    def create_payment(self, amount: int, description: str, user_id: int, subscription_type: str, payment_type: str = "new", subscription_id: Optional[int] = None) -> Dict[str, Any]:
        """Создание платежа в ЮKassa"""
        try:
            # Создаем уникальный ключ идемпотентности
            idempotence_key = str(uuid.uuid4())
            
            # Данные для создания платежа
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/SeaVPN_support_bot"
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": user_id,
                    "subscription_type": subscription_type,
                    "payment_type": payment_type,
                    "idempotence_key": idempotence_key,
                    **({"subscription_id": subscription_id} if subscription_id else {})
                },
                "receipt": {
                    "customer": {
                        "email": f"user_{user_id}@seavpn.com"
                    },
                    "items": [
                        {
                            "description": description,
                            "quantity": "1.00",
                            "amount": {
                                "value": f"{amount:.2f}",
                                "currency": "RUB"
                            },
                            "vat_code": "1",
                            "payment_mode": "full_payment",
                            "payment_subject": "service"
                        }
                    ]
                }
            }
            
            print(f"DEBUG: Отправляем платеж с суммой: {amount} -> {f'{amount:.2f}'}")
            print(f"DEBUG: payment_data: {payment_data}")
            
            # Создаем платеж через SDK
            payment = Payment.create(payment_data, idempotence_key)
            
            return {
                "success": True,
                "payment_id": payment.id,
                "confirmation_url": payment.confirmation.confirmation_url,
                "status": payment.status,
                "amount": amount,
                "description": description
            }
                    
        except Exception as e:
            print(f"Ошибка создания платежа: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Проверка статуса платежа"""
        try:
            logging.info(f"Получение статуса платежа в YooKassa для payment_id: {payment_id}")
            payment = Payment.find_one(payment_id)
            
            return {
                "success": True,
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.status == 'succeeded',
                "amount": float(payment.amount.value),
                "metadata": payment.metadata
            }
                    
        except Exception as e:
            logging.error(f"Ошибка check_payment_status({payment_id}): {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_receipt(self, payment_id: str, user_email: str, amount: int, description: str) -> Dict[str, Any]:
        """Создание чека для платежа"""
        try:
            # ЮKassa создает чеки автоматически при создании платежа
            print(f"Чек будет создан автоматически ЮKassa для платежа {payment_id}")
            return {
                "success": True,
                "message": "Чек будет создан автоматически ЮKassa"
            }
                    
        except Exception as e:
            print(f"Ошибка создания чека: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_payment_info(self, payment_id: str) -> Dict[str, Any]:
        """Получение полной информации о платеже"""
        try:
            payment = Payment.find_one(payment_id)
            
            return {
                "success": True,
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.status == 'succeeded',
                "amount": float(payment.amount.value),
                "currency": payment.amount.currency,
                "description": payment.description,
                "metadata": payment.metadata,
                "created_at": payment.created_at,
                "paid_at": payment.paid_at
            }
                    
        except Exception as e:
            print(f"Ошибка получения информации о платеже: {e}")
            return {
                "success": False,
                "error": str(e)
            }
