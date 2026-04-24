import asyncpg
import asyncio

from config import DB_HOST, DB_PORT, DB_PASSWORD, DB_NAME


async def check_database():
    try:
        # Проверяем подключение к базе
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user='postgres',
            password=DB_PASSWORD,
            # database=DB_NAME

        )

        # Проверяем существует ли база данных
        result = await conn.fetchval('''
            SELECT EXISTS(
                SELECT FROM pg_database WHERE datname = 'postgres'
            )
        ''')

        if result:
            print("✅ База данных  существует")
        else:
            print("❌ База данных  не существует")
            # Создаем базу данных
            await conn.execute('CREATE DATABASE bot_database')
            print("✅ База данных создана")

        await conn.close()

    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")


if __name__ == "__main__":
    asyncio.run(check_database())