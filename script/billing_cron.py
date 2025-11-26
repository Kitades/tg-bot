#!/usr/bin/env python3
import os
import sys
import uuid
import logging
from datetime import date
import config
import psycopg  # psycopg3
import requests


# ===================== Конфиг =====================

# Пример: postgresql://user:password@localhost:5432/mydb


# Реквизиты магазина ЮKassa


if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY:
    print("ERROR: SHOP_ID и/или SECRET_KEY не заданы в переменных окружения", file=sys.stderr)
    sys.exit(1)

# Карта типа подписки -> интервал для PostgreSQL
INTERVAL_MAP = {
    "regular": "1 month",
    "student": "1 month",
}


# ===================== Логирование =====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


# ===================== Работа с ЮKassa =====================

def charge_saved_method(
    user_id: int,
    yk_payment_method_id: str,
    amount: str,
    currency: str,
    subscription_id: int,
) -> dict:
    """
    Выполняет автосписание через ЮKassa по сохранённому способу оплаты.
    Возвращает JSON-ответ ЮKassa (или бросает исключение при HTTP-ошибке).
    """
    url = "https://api.yookassa.ru/v3/payments"

    # Идемпотентный ключ: завяжем на подписку и сегодняшнюю дату.
    idempotence_key = f"sub-{subscription_id}-{date.today().isoformat()}-{uuid.uuid4()}"

    payload = {
        "amount": {
            "value": amount,
            "currency": currency,
        },
        "capture": True,
        "payment_method_id": yk_payment_method_id,
        "description": f"Subscription #{subscription_id} for Telegram {user_id}",
        "metadata": {
            "user_id": user_id,
            "subscription_id": subscription_id,
            "purpose": "subscription_recurring",
        },
    }

    logging.info(
        "Создаём платёж в ЮKassa: subscription_id=%s, user_id=%s, amount=%s %s",
        subscription_id,
        user_id,
        amount,
        currency,
    )

    resp = requests.post(
        url,
        json=payload,
        auth=(config.YOOKASSA_SHOP_ID, config.YOOKASSA_SECRET_KEY),
        headers={"Idempotence-Key": idempotence_key},
        timeout=30,
    )

    # Если код ответа не 2xx — это ошибка на уровне HTTP
    if not (200 <= resp.status_code < 300):
        logging.error(
            "HTTP ошибка ЮKassa: status=%s, body=%s",
            resp.status_code,
            resp.text,
        )
        resp.raise_for_status()

    data = resp.json()
    status = data.get("status")
    logging.info("Ответ ЮKassa: payment_id=%s, status=%s", data.get("id"), status)

    return data


# ===================== Работа с БД =====================

def get_due_subscriptions(conn) -> list[dict]:
    """
    Возвращает список подписок, которые нужно списать сегодня.
    Фильтр: auto_renew=True и next_payment_date = текущая дата.
    """
    today = date.today()
    logging.info("Ищем подписки на дату %s", today.isoformat())

    query = """
        SELECT         
        id,
        user_id, 
        plan_type, 
        plan_name,
        price, 
        currency, 
        status,
        payment_status, 
        subscription_id, 
        auto_renew,
        metadata_json,
        start_date,
        end_date,
        created_at,
        updated_at,  
        payment_id,
        payment_method,
        next_payment_date
        FROM subscriptions
        WHERE auto_renew = True
          AND next_payment_date:: date = CURRENT_DATE
    """

    subs: list[dict] = []

    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

        for row in rows:
            (
                sub_id,
                user_id,
                plan_type,
                plan_name,
                price,
                currency,
                status,
                payment_status,
                subscription_id,
                auto_renew,
                metadata_json,
                start_date,
                end_date,
                created_at,
                updated_at,
                payment_id,
                payment_method,
                next_payment_date
            ) = row

            subs.append(
                {
                    "sub_id": sub_id,
                    "user_id": user_id,
                    "price": price,
                    "currency": currency,
                    "payment_id": payment_id,
                    "plan_type": plan_type,
                    "payment_method": payment_method,
                    "next_payment_date": next_payment_date,
                }
            )

    logging.info("Найдено %d подписок для списания", len(subs))
    return subs


def move_next_payment_date(conn, subscription_id: int, subscription_type: str):
    """
    Сдвигает next_payment_date в зависимости от типа подписки.
    По умолчанию — на 1 месяц (если тип неизвестен).
    """
    interval_str = INTERVAL_MAP.get(subscription_type, "1 month")

    logging.info(
        "Сдвигаем next_payment_date: subscription_id=%s, interval=%s",
        subscription_id,
        interval_str,
    )

    query = """
        UPDATE subscriptions
        SET next_payment_date = next_payment_date + CAST(%s AS INTERVAL)
        WHERE id = %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (interval_str, subscription_id))


def mark_subscription_failed(conn, subscription_id: int, reason: str):
    """
    Помечает подписку как 'failed' (или можно сделать поле last_error и т.п.).
    """
    logging.warning(
        "Помечаем подписку как failed: subscription_id=%s, reason=%s",
        subscription_id,
        reason,
    )

    query = """
        UPDATE subscriptions
        SET status = 'expired', auto_renew = False
        WHERE id = %s
    """

    with conn.cursor() as cur:
        cur.execute(query, (subscription_id,))


# ===================== Основная логика =====================

def main():
    logging.info("=== Запуск биллингового крона ===")

    try:
        # autocommit=True, чтобы не думать о транзакциях в cron-скрипте
        with psycopg.connect(config.DATABASE_URL_SYNC, autocommit=True) as conn:
            due_subs = get_due_subscriptions(conn)

            for sub in due_subs:
                sub_id = sub["sub_id"]
                user_id = sub["user_id"]
                price = sub["price"]
                currency = sub["currency"]
                payment_id = sub["payment_id"]
                payment_method = sub["payment_method"]
                plan_type = sub["plan_type"]

                # ЮKassa ожидает строку для amount
                amount_str = f"{price:.2f}"

                try:
                    payment = charge_saved_method(
                        user_id=user_id,
                        yk_payment_method_id=payment_method,
                        amount=amount_str,
                        currency=currency,
                        subscription_id=sub_id,
                    )
                except Exception as e:
                    logging.exception(
                        "Ошибка при попытке списания: subscription_id=%s, error=%s",
                        sub_id,
                        e,
                    )
                    # Помечаем подписку как failed (или можно этого не делать, по бизнес-логике)
                    mark_subscription_failed(conn, sub_id, reason=str(e))
                    continue

                status = payment.get("status")
                if status == "succeeded":
                    # Всё хорошо — переносим next_payment_date
                    move_next_payment_date(conn, sub_id, plan_type)
                else:
                    # ЮKassa ответила, но платёж не прошёл (canceled, pending и т.п.)
                    # todo придумать
                    reason = f"Payment status {status}"
                    mark_subscription_failed(conn, sub_id, reason=reason)

    except Exception:
        logging.exception("Критическая ошибка при выполнении крона")
        sys.exit(1)

    logging.info("=== Завершение биллингового крона ===")


if __name__ == "__main__":
    main()
