import asyncio
from sqlalchemy import text
from database.session import engine, Base, get_db_session_sync, get_db_session


async def check_subscriptions_table_structure():
    """Проверяем структуру таблицы subscriptions"""
    async with get_db_session() as session:
        result = await session.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'subscriptions'
            ORDER BY ordinal_position
        """))

        print("📋 Структура таблицы subscriptions:")
        for row in result.fetchall():
            print(f"  {row[0]} ({row[1]}, nullable: {row[2]})")


async def recreate_tables():
    """Полное пересоздание таблиц согласно моделям SQLAlchemy"""
    async with engine.begin() as conn:
        # Удаляем старые таблицы
        await conn.run_sync(Base.metadata.drop_all)
        # Создаем новые таблицы по моделям
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Таблицы пересозданы согласно моделям")


async def fix_database_structure():
    """Исправляем структуру базы данных"""
    print("🔧 Исправляем структуру базы данных...")

    # 1. Проверяем текущую структуру
    await check_subscriptions_table_structure()

    # 2. Пересоздаем таблицы
    await recreate_tables()

    # 3. Проверяем что все работает
    await verify_tables_structure()


async def verify_tables_structure():
    """Проверяем что структура таблиц правильная"""
    async with get_db_session_sync() as session:
        # Проверяем таблицу users
        result = await session.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('user_id', 'telegram_id', 'username', 'full_name')
        """))
        users_columns_ok = result.scalar() == 4

        # Проверяем таблицу subscriptions
        result = await session.execute(text("""
            SELECT COUNT(*) FROM information_schema.columns 
            WHERE table_name = 'subscriptions' 
            AND column_name IN ('id', 'user_id', 'plan_type', 'status', 'end_date')
        """))
        subs_columns_ok = result.scalar() == 5

        print(f"✅ Таблица users: {'OK' if users_columns_ok else 'ERROR'}")
        print(f"✅ Таблица subscriptions: {'OK' if subs_columns_ok else 'ERROR'}")

        if users_columns_ok and subs_columns_ok:
            print("🎉 Структура базы данных правильная!")
        else:
            print("❌ Есть проблемы со структурой базы данных")


if __name__ == "__main__":
    asyncio.run(fix_database_structure())
