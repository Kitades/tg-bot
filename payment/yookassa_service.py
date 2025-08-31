import aiohttp
import uuid
import json
from datetime import datetime
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_WEBHOOK_URL


class YooKassaService:
    def __init__(self):
        self.base_url = "https://api.yookassa.ru/v3"
        self.auth = aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
        self.headers = {
            'Idempotence-Key': None,
            'Content-Type': 'application/json'
        }

    async def create_payment(self, subscription_id: int, amount: float, user_id: int,
                             description: str = "Оплата подписки") -> dict:
        """Создает платеж в ЮКассе"""
        payment_id = str(uuid.uuid4())

        payload = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/your_bot_username?start=success_{subscription_id}"
            },
            "capture": True,
            "description": description,
            "metadata": {
                "subscription_id": subscription_id,
                "user_id": user_id
            },
            "receipt": {
                "customer": {
                    "email": "user@example.com"  # Можно получить из профиля пользователя
                },
                "items": [
                    {
                        "description": "Подписка на информационный канал по стоматологии",
                        "quantity": "1",
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

        async with aiohttp.ClientSession() as session:
            self.headers['Idempotence-Key'] = payment_id
            async with session.post(
                    f"{self.base_url}/payments",
                    json=payload,
                    auth=self.auth,
                    headers=self.headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'payment_id': data['id'],
                        'confirmation_url': data['confirmation']['confirmation_url'],
                        'status': data['status']
                    }
                else:
                    error_text = await response.text()
                    raise Exception(f"YooKassa error: {response.status} - {error_text}")

    async def check_payment(self, payment_id: str) -> dict:
        """Проверяет статус платежа"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f"{self.base_url}/payments/{payment_id}",
                    auth=self.auth
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'status': data['status'],
                        'paid': data.get('paid', False),
                        'amount': data['amount']['value'],
                        'metadata': data.get('metadata', {})
                    }
                else:
                    error_text = await response.text()
                    raise Exception(f"YooKassa error: {response.status} - {error_text}")

    async def process_webhook(self, data: dict) -> dict:
        """Обрабатывает вебхук от ЮКассы"""
        event = data.get('event')
        payment_data = data.get('object', {})

        if event == 'payment.succeeded':
            return {
                'success': True,
                'payment_id': payment_data['id'],
                'subscription_id': payment_data['metadata'].get('subscription_id'),
                'user_id': payment_data['metadata'].get('user_id'),
                'amount': payment_data['amount']['value'],
                'paid': True
            }

        return {'success': False, 'event': event}


# Создаем экземпляр сервиса
yookassa_service = YooKassaService()