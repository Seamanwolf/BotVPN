# Интеграция с YooKassa

## Настройка YooKassa

### 1. Создание магазина в YooKassa
1. Зарегистрируйтесь на https://yookassa.ru/
2. Создайте магазин
3. Получите Shop ID и Secret Key

### 2. Добавление настроек в .env
```bash
# YooKassa Configuration
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
YOOKASSA_WEBHOOK_URL=https://your-domain.com/webhook/yookassa
```

## Интеграция в бота

### 1. Установка зависимостей
```bash
pip3 install yookassa
```

### 2. Создание модуля для работы с YooKassa
```python
# yookassa_client.py
from yookassa import Configuration, Payment
from yookassa.domain.request import PaymentRequest
from yookassa.domain.common import Currency
import uuid

class YooKassaClient:
    def __init__(self, shop_id: str, secret_key: str):
        Configuration.account_id = shop_id
        Configuration.secret_key = secret_key
    
    def create_payment(self, amount: float, description: str, user_id: int):
        """Создание платежа"""
        payment_request = PaymentRequest(
            amount={
                "value": str(amount),
                "currency": Currency.RUB
            },
            confirmation={
                "type": "redirect",
                "return_url": "https://t.me/your_bot_username"
            },
            capture=True,
            description=description,
            metadata={
                "user_id": user_id
            }
        )
        
        payment = Payment.create(payment_request)
        return payment
```

### 3. Обновление обработчика покупки
```python
# В bot.py добавить:
from yookassa_client import YooKassaClient

yookassa = YooKassaClient(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

@dp.message(F.text.contains("месяц"))
async def tariff_handler(message: Message):
    # ... существующий код ...
    
    # Создаем платеж в YooKassa
    payment = yookassa.create_payment(
        amount=price,
        description=f"VPN подписка {TARIFFS[tariff]['name']}",
        user_id=user.id
    )
    
    # Сохраняем информацию о платеже
    db = SessionLocal()
    try:
        payment_record = Payment(
            user_id=user.id,
            provider="yookassa",
            invoice_id=payment.id,
            amount=price * 100,  # в копейках
            status="pending"
        )
        db.add(payment_record)
        db.commit()
    finally:
        db.close()
    
    # Отправляем ссылку на оплату
    await message.answer(
        f"💳 Оплата\n\n"
        f"Тариф: {TARIFFS[tariff]['name']}\n"
        f"Сумма: {price}₽\n\n"
        f"Для оплаты перейдите по ссылке:\n"
        f"{payment.confirmation.confirmation_url}\n\n"
        f"После оплаты подписка будет активирована автоматически.",
        reply_markup=get_main_menu_keyboard()
    )
```

### 4. Webhook для обработки платежей
```python
# webhook.py
from fastapi import FastAPI, Request
from yookassa.domain.notification import WebhookNotification
import json

app = FastAPI()

@app.post("/webhook/yookassa")
async def yookassa_webhook(request: Request):
    """Обработка webhook от YooKassa"""
    body = await request.body()
    event_json = json.loads(body)
    
    notification = WebhookNotification(event_json)
    
    if notification.event == "payment.succeeded":
        payment_id = notification.object.id
        metadata = notification.object.metadata
        
        # Активируем подписку
        await activate_subscription(payment_id, metadata.get("user_id"))
    
    return {"status": "ok"}
```

## Запуск с YooKassa

### 1. Обновить requirements.txt
```
yookassa==3.0.0
fastapi==0.104.1
uvicorn==0.24.0
```

### 2. Запуск webhook сервера
```bash
uvicorn webhook:app --host 0.0.0.0 --port 8000
```

### 3. Настройка webhook в YooKassa
1. В личном кабинете YooKassa
2. Перейдите в настройки магазина
3. Добавьте webhook URL: `https://your-domain.com/webhook/yookassa`

## Тестирование

### Тестовые карты YooKassa:
- **Успешная оплата**: 1111 1111 1111 1026
- **Недостаточно средств**: 1111 1111 1111 1047
- **Карта заблокирована**: 1111 1111 1111 1101

### Тестовые данные:
- Срок действия: любой будущий
- CVV: любой 3-значный код
- 3D Secure: 123456

## Безопасность

### Рекомендации:
1. Используйте HTTPS для webhook
2. Проверяйте подпись webhook
3. Храните секретные ключи в безопасном месте
4. Логируйте все платежи
5. Регулярно проверяйте статус платежей

### Проверка подписи webhook:
```python
import hmac
import hashlib

def verify_webhook_signature(body: bytes, signature: str, secret: str):
    """Проверка подписи webhook"""
    expected_signature = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)
```
