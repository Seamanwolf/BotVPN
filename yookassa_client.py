import uuid
import httpx
import base64
from datetime import datetime
from typing import Optional, Dict, Any
from config import YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID

class YooKassaClient:
    def __init__(self):
        self.secret_key = YOOKASSA_SECRET_KEY
        self.shop_id = YOOKASSA_SHOP_ID
        self.base_url = "https://api.yookassa.ru/v3"
        
        # Создаем Basic Auth заголовок
        credentials = f"{self.shop_id}:{self.secret_key}"
        self.auth_header = f"Basic {base64.b64encode(credentials.encode()).decode()}"
        
    async def create_payment(self, amount: float, description: str, user_id: int, subscription_type: str) -> Dict[str, Any]:
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
                    "idempotence_key": idempotence_key
                },
                "receipt": {
                    "customer": {
                        "email": f"user_{user_id}@seavpn.com"
                    },
                    "items": [
                        {
                            "description": description,
                            "quantity": "1",
                            "amount": {
                                "value": f"{amount:.2f}",
                                "currency": "RUB"
                            },
                            "vat_code": 1,
                            "payment_subject_type": "service",
                            "payment_mode_type": "full_payment"
                        }
                    ]
                }
            }
            
            # Отправляем запрос на создание платежа
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/payments",
                    json=payment_data,
                    headers={
                        "Authorization": self.auth_header,
                        "Idempotence-Key": idempotence_key,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    payment_info = response.json()
                    return {
                        "success": True,
                        "payment_id": payment_info["id"],
                        "confirmation_url": payment_info["confirmation"]["confirmation_url"],
                        "status": payment_info["status"],
                        "amount": amount,
                        "description": description
                    }
                else:
                    print(f"Ошибка создания платежа: {response.status_code} - {response.text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }
                    
        except Exception as e:
            print(f"Ошибка создания платежа: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Проверка статуса платежа"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/payments/{payment_id}",
                    headers={
                        "Authorization": self.auth_header,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    payment_info = response.json()
                    return {
                        "success": True,
                        "payment_id": payment_info["id"],
                        "status": payment_info["status"],
                        "paid": payment_info["paid"],
                        "amount": float(payment_info["amount"]["value"]),
                        "metadata": payment_info.get("metadata", {})
                    }
                else:
                    print(f"Ошибка проверки статуса платежа: {response.status_code} - {response.text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }
                    
        except Exception as e:
            print(f"Ошибка проверки статуса платежа: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def create_receipt(self, payment_id: str, user_email: str, amount: float, description: str) -> Dict[str, Any]:
        """Создание чека для платежа"""
        try:
            receipt_data = {
                "customer": {
                    "email": user_email
                },
                "items": [
                    {
                        "description": description,
                        "quantity": "1",
                        "amount": {
                            "value": f"{amount:.2f}",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_subject_type": "service",
                        "payment_mode_type": "full_payment"
                    }
                ]
            }
            
            async with httpx.AsyncClient() as client:
                # ЮKassa не поддерживает создание чеков через API для физ. лиц
                # Чек создается автоматически при создании платежа
                print(f"Чек будет создан автоматически ЮKassa для платежа {payment_id}")
                return {
                    "success": True,
                    "message": "Чек будет создан автоматически ЮKassa"
                }
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "Чек успешно создан"
                    }
                else:
                    print(f"Ошибка создания чека: {response.status_code} - {response.text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }
                    
        except Exception as e:
            print(f"Ошибка создания чека: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_payment_info(self, payment_id: str) -> Dict[str, Any]:
        """Получение полной информации о платеже"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/payments/{payment_id}",
                    headers={
                        "Authorization": self.auth_header,
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    payment_info = response.json()
                    return {
                        "success": True,
                        "payment_id": payment_info["id"],
                        "status": payment_info["status"],
                        "paid": payment_info["paid"],
                        "amount": float(payment_info["amount"]["value"]),
                        "currency": payment_info["amount"]["currency"],
                        "description": payment_info.get("description", ""),
                        "metadata": payment_info.get("metadata", {}),
                        "created_at": payment_info.get("created_at"),
                        "paid_at": payment_info.get("paid_at")
                    }
                else:
                    print(f"Ошибка получения информации о платеже: {response.status_code} - {response.text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }
                    
        except Exception as e:
            print(f"Ошибка получения информации о платеже: {e}")
            return {
                "success": False,
                "error": str(e)
            }
