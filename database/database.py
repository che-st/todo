from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

# Создаем асинхронный движок для SQLite[citation:2]
engine = create_async_engine(
    url='sqlite+aiosqlite:///data/bot.db',  # Файл базы данных
    echo=False  # Установите True для отладки SQL-запросов
)

# Фабрика сессий для работы с БД
async_session = async_sessionmaker(
    engine, 
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс для всех моделей"""
    pass

async def create_tables():
    """Создание таблиц в базе данных"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
