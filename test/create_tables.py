import asyncpg
import asyncio

from config import DB_PASSWORD, DB_PORT, DB_HOST, DB_NAME


async def create_tables_manually():
    """Создание таблиц вручную через asyncpg"""
    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user='postgres',
        password=DB_PASSWORD
    )

    try:
        # Создаем таблицу users
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                username VARCHAR(100),
                full_name VARCHAR(200) NOT NULL,
                language_code VARCHAR(10) DEFAULT 'ru',
                is_premium BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Создаем таблицу subscriptions
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                plan_type VARCHAR(50) NOT NULL,
                plan_name VARCHAR(100) NOT NULL,
                price NUMERIC(10,2) NOT NULL,
                currency VARCHAR(3) DEFAULT 'RUB',
                status VARCHAR(20) DEFAULT 'pending',
                payment_status VARCHAR(20) DEFAULT 'pending',
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                payment_id VARCHAR(100) UNIQUE,
                payment_method VARCHAR(50),
                auto_renew BOOLEAN DEFAULT FALSE,
                renew_attempts INTEGER DEFAULT 0,
                last_renew_attempt TIMESTAMP
            )
        ''')

        print("✅ Таблицы созданы успешно!")

    except Exception as e:
        print(f"❌ Ошибка создания таблиц: {e}")
    finally:
        await conn.close()


async def main():
    await create_tables_manually()


if __name__ == "__main__":
    asyncio.run(main())