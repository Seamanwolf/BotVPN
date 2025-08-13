import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from yookassa import Payment
from yookassa.domain.request import PaymentRequest
from yookassa.domain.models import Receipt, ReceiptItem, Amount
from config import YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID

class YooKassaClient:
    def __init__(self):
        self.secret_key = YOOKASSA_SECRET_KEY
        self.shop_id = YOOKASSA_SHOP_ID
        
    def create_payment(self, amount: float, description: str, user_id: int, subscription_type: str) -> Dict[str, Any]:
        """Создание платежа в ЮKassa"""
        try:
            # Создаем уникальный ID платежа
            payment_id = str(uuid.uuid4())
            
            # Создаем запрос на платеж
            payment_request = PaymentRequest(
                amount=Amount(
                    value=str(amount),
                    currency="RUB"
                ),
                confirmation={
                    "type": "redirect",
                    "return_url": "https://t.me/SeaVPN_support_bot"
                },
                capture=True,
                description=description,
                metadata={
                    "user_id": user_id,
                    "subscription_type": subscription_type,
                    "payment_id": payment_id
                },
                receipt={
                    "customer": {
                        "email": f"user_{user_id}@seavpn.com"
                    },
                    "items": [
                        {
                            "description": description,
                            "quantity": "1",
                            "amount": {
                                "value": str(amount),
                                "currency": "RUB"
                            },
                            "vat_code": 1,
                            "payment_subject_type": "service",
                            "payment_mode_type": "full_payment"
                        }
                    ]
                }
            )
            
            # Создаем платеж
            payment = Payment.create(payment_request, self.secret_key)
            
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
            payment = Payment.find_one(payment_id, self.secret_key)
            
            return {
                "success": True,
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.paid,
                "amount": float(payment.amount.value),
                "metadata": payment.metadata
            }
            
        except Exception as e:
            print(f"Ошибка проверки статуса платежа: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def create_receipt(self, payment_id: str, user_email: str, amount: float, description: str) -> Dict[str, Any]:
        """Создание чека для платежа"""
        try:
            # Создаем чек
            receipt = Receipt(
                customer={
                    "email": user_email
                },
                items=[
                    ReceiptItem(
                        description=description,
                        quantity="1",
                        amount=Amount(
                            value=str(amount),
                            currency="RUB"
                        ),
                        vat_code=1,
                        payment_subject_type="service",
                        payment_mode_type="full_payment"
                    )
                ]
            )
            
            # Привязываем чек к платежу
            Payment.create_receipt(payment_id, receipt, self.secret_key)
            
            return {
                "success": True,
                "message": "Чек успешно создан"
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
            payment = Payment.find_one(payment_id, self.secret_key)
            
            return {
                "success": True,
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.paid,
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
