import hmac, hashlib, json, requests

from config import YOOKASSA_SECRET_KEY

URL = "http://localhost:8000/yookassa_webhook"
SECRET = YOOKASSA_SECRET_KEY


def test():
    payload = {
        "event": "payment.succeeded",
        "object": {
            "id": "test_pay_123",
            "amount": {"value": "100.00", "currency": "RUB"},
            "payment_method": {"id": "pm_1"},
            "metadata": {"user_id": 12345, "type": "initial_subscription", "plan_type": "regular"}
        }
    }

    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature
    }

    r = requests.post(URL, data=body, headers=headers)
    return print(r.status_code, r.text)
