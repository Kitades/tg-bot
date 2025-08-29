from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
from config import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

# URL подключения для asyncpg
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Создаем асинхронный engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    poolclass=NullPool,
    future=True
)

# Создаем фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Базовый класс для моделей
Base = declarative_base()


@asynccontextmanager
async def get_db_session():
    """Асинхронный контекстный менеджер для сессий"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def create_tables():
    """Создание таблиц в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Таблицы созданы успешно")


async def check_connection():
    """Проверка подключения к базе данных"""
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        print("✅ Подключение к PostgreSQL успешно")
        return True
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False


async def get_db_session_sync():
    """Синхронное получение сессии для фоновых задач"""
    return AsyncSessionLocal()
