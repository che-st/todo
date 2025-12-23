from sqlalchemy import BigInteger, Integer, Text, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .database import Base

class User(Base):
    """Модель пользователя Telegram"""
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    
    # Связь с задачами (один пользователь - много задач)
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="user", cascade="all, delete-orphan")

class Task(Base):
    """Модель задачи"""
    __tablename__ = 'tasks'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # Дедлайн задачи
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # Связи
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    reminders: Mapped[list["Reminder"]] = relationship("Reminder", back_populates="task", cascade="all, delete-orphan")

class Reminder(Base):
    """Модель напоминания"""
    __tablename__ = 'reminders'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id'), nullable=False)
    reminder_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    
    # Связь с задачей
    task: Mapped["Task"] = relationship("Task", back_populates="reminders")
