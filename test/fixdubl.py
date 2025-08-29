from sqlalchemy import text  # Добавляем импорт text
import asyncio
from database.session import get_db_session


async def check_duplicate_users():
    """Проверяем есть ли дубликаты пользователей"""
    async with get_db_session() as session:
        # ИСПРАВЛЕНИЕ: используем text() для сырого SQL
        result = await session.execute(text("""
            SELECT telegram_id, COUNT(*) 
            FROM users 
            GROUP BY telegram_id 
            HAVING COUNT(*) > 1
        """))
        duplicates = result.fetchall()

        if duplicates:
            print("⚠️ Найдены дубликаты пользователей:")
            for telegram_id, count in duplicates:
                print(f"Telegram ID: {telegram_id}, Количество: {count}")
            return duplicates
        else:
            print("✅ Дубликатов не найдено")
            return []


async def remove_duplicate_users():
    """Удаляем дубликаты пользователей"""
    async with get_db_session() as session:
        try:
            # ИСПРАВЛЕНИЕ: используем text() для сырого SQL
            result = await session.execute(text("""
                DELETE FROM users 
                WHERE user_id NOT IN (
                    SELECT MIN(user_id) 
                    FROM users 
                    GROUP BY telegram_id
                )
            """))

            deleted_count = result.rowcount
            if deleted_count > 0:
                print(f"✅ Удалено {deleted_count} дубликатов пользователей")
            else:
                print("✅ Дубликатов для удаления не найдено")

            await session.commit()
            return deleted_count

        except Exception as e:
            print(f"❌ Ошибка при удалении дубликатов: {e}")
            await session.rollback()
            return 0


async def add_unique_constraint():
    """Добавляем ограничение уникальности для telegram_id"""
    async with get_db_session() as session:
        try:
            # ИСПРАВЛЕНИЕ: используем text() для сырого SQL
            await session.execute(text("""
                ALTER TABLE users 
                ADD CONSTRAINT unique_telegram_id UNIQUE (telegram_id)
            """))
            print("✅ Ограничение уникальности добавлено")
            await session.commit()

        except Exception as e:
            print(f"❌ Ошибка при добавлении ограничения: {e}")
            # Если ограничение уже существует, это нормально
            if "already exists" in str(e):
                print("ℹ️ Ограничение уже существует")
            await session.rollback()


async def fix_duplicates_problem():
    """Полное исправление проблемы с дубликатами"""
    print("🔧 Начинаем исправление проблемы с дубликатами...")

    # 1. Проверяем дубликаты
    print("1. Проверяем наличие дубликатов...")
    duplicates = await check_duplicate_users()

    if not duplicates:
        print("✅ Проблема с дубликатами не обнаружена")
        return

    # 2. Удаляем дубликаты
    print("2. Удаляем дубликаты...")
    await remove_duplicate_users()

    # 3. Добавляем ограничение уникальности
    print("3. Добавляем ограничение уникальности...")
    await add_unique_constraint()

    # 4. Проверяем результат
    print("4. Проверяем результат...")
    remaining_duplicates = await check_duplicate_users()

    if not remaining_duplicates:
        print("🎉 Проблема с дубликатами успешно решена!")
    else:
        print("❌ Не удалось полностью решить проблему с дубликатами")


async def check_database_health():
    """Проверка здоровья базы данных"""
    async with get_db_session() as session:
        try:
            # Простая проверка что база работает
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            print(f"📊 Всего пользователей в базе: {user_count}")

            # Проверяем ограничение уникальности
            result = await session.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT telegram_id, COUNT(*) 
                    FROM users 
                    GROUP BY telegram_id 
                    HAVING COUNT(*) > 1
                ) AS duplicates
            """))
            duplicate_count = result.scalar()
            print(f"🔍 Найдено групп с дубликатами: {duplicate_count}")

        except Exception as e:
            print(f"❌ Ошибка проверки здоровья базы: {e}")

if __name__ == "__main__":
    print("🚀 Запуск исправления проблемы с дубликатами...")
    asyncio.run(fix_duplicates_problem())
    asyncio.run(check_database_health())