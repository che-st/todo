from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from .models import User, Task, Reminder
from .database import async_session

async def get_or_create_user(session: AsyncSession, user_id: int, username: str = None, full_name: str = None) -> User:
    """Получить пользователя или создать нового"""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(id=user_id, username=username, full_name=full_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    
    return user

async def create_task(session: AsyncSession, user_id: int, text: str, deadline: datetime = None) -> Task:
    """Создать новую задачу"""
    task = Task(
        user_id=user_id,
        text=text,
        deadline=deadline,
        created_at=datetime.now()
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task

async def get_user_tasks(session: AsyncSession, user_id: int, completed: bool = None) -> list[Task]:
    """Получить задачи пользователя"""
    query = select(Task).where(Task.user_id == user_id)
    
    if completed is not None:
        query = query.where(Task.completed == completed)
    
    query = query.order_by(Task.created_at.desc())
    
    result = await session.execute(query)
    return result.scalars().all()
