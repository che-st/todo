import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv('BOT_TOKEN'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler()

# Хранилище задач (в реальном проекте используйте базу данных)
tasks_storage: Dict[int, List[Dict]] = {}
# Хранилище напоминаний
reminders_storage: Dict[str, Dict] = {}

# Файлы для сохранения данных
DATA_FILE = "tasks_data.json"
REMINDERS_FILE = "reminders_data.json"

# Состояния FSM
class TaskStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_deadline = State()
    waiting_for_reminder = State()
    waiting_for_task_edit = State()
    waiting_for_deadline_edit = State()

# Загрузка данных из файла
def load_data():
    global tasks_storage, reminders_storage
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            tasks_storage = json.load(f)
            tasks_storage = {int(k): v for k, v in tasks_storage.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        tasks_storage = {}
    
    try:
        with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
            reminders_storage = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        reminders_storage = {}

# Сохранение данных в файл
def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks_storage, f, ensure_ascii=False, indent=2)
    
    with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reminders_storage, f, ensure_ascii=False, indent=2)

# Функция для парсинга времени из текста
def parse_time(time_str: str) -> Optional[datetime]:
    """Парсит время из строки в разных форматах"""
    time_str = time_str.lower().strip()
    now = datetime.now()
    
    # Паттерны для парсинга
    patterns = [
        # Завтра в 15:30
        (r'завтра в (\d{1,2}):(\d{2})', lambda m: now.replace(
            hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0
        ) + timedelta(days=1)),
        
        # Сегодня в 18:00
        (r'сегодня в (\d{1,2}):(\d{2})', lambda m: now.replace(
            hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0
        )),
        
        # Через 2 часа
        (r'через (\d+) час(?:а|ов)?', lambda m: now + timedelta(hours=int(m.group(1)))),
        
        # Через 30 минут
        (r'через (\d+) минут(?:у|ы)?', lambda m: now + timedelta(minutes=int(m.group(1)))),
        
        # Через 3 дня
        (r'через (\d+) день(?:|я|ей)', lambda m: now + timedelta(days=int(m.group(1)))),
        
        # 2024-12-31 23:59
        (r'(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{2})', 
         lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 
                           int(m.group(4)), int(m.group(5)))),
        
        # 31.12.2024 23:59
        (r'(\d{1,2})\.(\d{1,2})\.(\d{4}) (\d{1,2}):(\d{2})',
         lambda m: datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                           int(m.group(4)), int(m.group(5)))),
        
        # 31 декабря 2024 23:59
        (r'(\d{1,2}) (\w+) (\d{4}) (\d{1,2}):(\d{2})',
         lambda m: parse_russian_date(m)),
        
        # Просто время 15:30 (сегодня)
        (r'^(\d{1,2}):(\d{2})$', 
         lambda m: now.replace(hour=int(m.group(1)), minute=int(m.group(2)), 
                              second=0, microsecond=0)),
    ]
    
    for pattern, handler in patterns:
        match = re.match(pattern, time_str)
        if match:
            try:
                result = handler(match)
                if result > now:
                    return result
                else:
                    # Если время уже прошло, добавляем день
                    if pattern == patterns[-1][0]:  # Для формата "15:30"
                        result += timedelta(days=1)
                        return result
            except Exception:
                continue
    
    return None

# Функция для парсинга русских дат
def parse_russian_date(match):
    months = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    
    day = int(match.group(1))
    month_str = match.group(2).lower()
    year = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    
    month = months.get(month_str)
    if month:
        return datetime(year, month, day, hour, minute)
    raise ValueError("Неверное название месяца")

# Функция для создания клавиатуры с задачами
def create_tasks_keyboard(user_id: int, task_index: int = None):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if user_id in tasks_storage and tasks_storage[user_id]:
        for i, task in enumerate(tasks_storage[user_id]):
            status = "✅" if task['completed'] else "⭕"
            icon = "⏰" if task.get('deadline') else "📝"
            button_text = f"{status}{icon} {task['text'][:25]}"
            
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_task_{i}"
                )
            ])
    
    # Кнопки действий
    action_buttons = []
    action_buttons.append(InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task"))
    
    if task_index is not None and user_id in tasks_storage and 0 <= task_index < len(tasks_storage[user_id]):
        task = tasks_storage[user_id][task_index]
        if not task['completed']:
            action_buttons.append(InlineKeyboardButton(text="⏰ Напоминание", callback_data=f"set_reminder_{task_index}"))
            action_buttons.append(InlineKeyboardButton(text="📅 Дедлайн", callback_data=f"set_deadline_{task_index}"))
    
    action_buttons.append(InlineKeyboardButton(text="🗑️ Очистить выполненные", callback_data="clear_completed"))
    action_buttons.append(InlineKeyboardButton(text="📋 Все задачи", callback_data="show_all_tasks"))
    
    # Добавляем кнопки по 2 в ряд
    for i in range(0, len(action_buttons), 2):
        keyboard.inline_keyboard.append(action_buttons[i:i+2])
    
    return keyboard

# Функция для форматирования времени
def format_time(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")

# Функция для форматирования дедлайна
def format_deadline(deadline_str: str) -> str:
    try:
        deadline = datetime.fromisoformat(deadline_str)
        now = datetime.now()
        
        if deadline < now:
            return "❌ Просрочено"
        
        delta = deadline - now
        
        if delta.days > 7:
            return f"📅 {format_time(deadline)}"
        elif delta.days > 1:
            return f"📅 Через {delta.days} дней"
        elif delta.days == 1:
            return f"📅 Завтра в {deadline.strftime('%H:%M')}"
        elif delta.days == 0:
            hours = delta.seconds // 3600
            if hours > 0:
                return f"⏰ Через {hours} час."
            else:
                minutes = delta.seconds // 60
                if minutes > 0:
                    return f"⏰ Через {minutes} мин."
                else:
                    return f"⏰ Сейчас"
    except Exception:
        return "📅 Без дедлайна"

# Функция отправки напоминания
async def send_reminder(user_id: int, task_text: str, reminder_id: str):
    try:
        await bot.send_message(
            user_id,
            f"🔔 *Напоминание!*\n\nЗадача: *{task_text}*\n\n"
            f"Не забудьте выполнить задачу!",
            parse_mode="Markdown"
        )
        
        # Удаляем напоминание из хранилища
        if reminder_id in reminders_storage:
            del reminders_storage[reminder_id]
            save_data()
            
    except Exception as e:
        print(f"Ошибка при отправке напоминания: {e}")

# Функция для создания напоминания
def create_reminder(user_id: int, task_index: int, reminder_time: datetime, task_text: str):
    reminder_id = f"{user_id}_{task_index}_{reminder_time.timestamp()}"
    
    # Сохраняем напоминание
    reminders_storage[reminder_id] = {
        'user_id': user_id,
        'task_index': task_index,
        'reminder_time': reminder_time.isoformat(),
        'task_text': task_text
    }
    
    # Планируем отправку
    scheduler.add_job(
        send_reminder,
        trigger=DateTrigger(run_date=reminder_time),
        args=[user_id, task_text, reminder_id],
        id=reminder_id
    )
    
    save_data()
    return reminder_id

# Загрузка и планирование существующих напоминаний при старте
def load_and_schedule_reminders():
    for reminder_id, reminder_data in list(reminders_storage.items()):
        try:
            reminder_time = datetime.fromisoformat(reminder_data['reminder_time'])
            
            if reminder_time > datetime.now():
                scheduler.add_job(
                    send_reminder,
                    trigger=DateTrigger(run_date=reminder_time),
                    args=[reminder_data['user_id'], 
                          reminder_data['task_text'], 
                          reminder_id],
                    id=reminder_id
                )
            else:
                # Удаляем просроченные напоминания
                del reminders_storage[reminder_id]
        except Exception as e:
            print(f"Ошибка при загрузке напоминания: {e}")
    
    save_data()

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in tasks_storage:
        tasks_storage[user_id] = []
        save_data()
    
    welcome_text = (
        "📝 *To-Do List Bot с напоминаниями*\n\n"
        "*Основные команды:*\n"
        "/start - Начать работу\n"
        "/add - Добавить задачу с дедлайном\n"
        "/list - Показать все задачи\n"
        "/deadlines - Показать задачи с дедлайнами\n"
        "/reminders - Показать активные напоминания\n"
        "/help - Помощь\n\n"
        "*Быстрые действия:*\n"
        "• Отправьте текст задачи, чтобы добавить\n"
        "• Используйте кнопки для управления\n"
        "• Нажмите на задачу для детального просмотра"
    )
    
    await message.answer(welcome_text, parse_mode="Markdown")

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 *Помощь по боту*\n\n"
        "*Форматы времени:*\n"
        "• `сегодня в 18:00`\n"
        "• `завтра в 15:30`\n"
        "• `31.12.2024 23:59`\n"
        "• `через 2 часа`\n"
        "• `через 30 минут`\n"
        "• `15:30` (сегодня)\n\n"
        "*Команды:*\n"
        "/add - Добавить задачу\n"
        "/deadlines - Задачи с дедлайнами\n"
        "/reminders - Мои напоминания\n"
        "/clear - Очистить выполненные\n"
        "/help - Эта справка"
    )
    await message.answer(help_text, parse_mode="Markdown")

# Команда /add
@dp.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите текст новой задачи:")
    await state.set_state(TaskStates.waiting_for_task)

# Обработка текста задачи
@dp.message(TaskStates.waiting_for_task)
async def process_task_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    task_text = message.text.strip()
    
    if not task_text:
        await message.answer("❌ Текст задачи не может быть пустым!")
        return
    
    await state.update_data(task_text=task_text)
    
    # Предлагаем установить дедлайн
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Добавить дедлайн", callback_data="add_deadline"),
            InlineKeyboardButton(text="📝 Без дедлайна", callback_data="skip_deadline")
        ]
    ])
    
    await message.answer(
        f"✅ Задача сохранена: *{task_text}*\n\n"
        "Хотите добавить дедлайн для задачи?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# Обработка добавления дедлайна
@dp.callback_query(F.data.in_(["add_deadline", "skip_deadline"]))
async def process_deadline_choice(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "skip_deadline":
        # Создаем задачу без дедлайна
        data = await state.get_data()
        user_id = callback.from_user.id
        
        if user_id not in tasks_storage:
            tasks_storage[user_id] = []
        
        new_task = {
            'text': data['task_text'],
            'completed': False,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'completed_at': None,
            'deadline': None,
            'reminders': []
        }
        
        tasks_storage[user_id].append(new_task)
        save_data()
        
        await callback.message.edit_text(
            f"✅ Задача добавлена: *{data['task_text']}*\n"
            "📅 Без дедлайна",
            parse_mode="Markdown"
        )
        
        await show_task_list(callback.message)
        await state.clear()
        
    else:
        await callback.message.edit_text(
            "📅 Введите дедлайн для задачи:\n\n"
            "*Примеры:*\n"
            "• сегодня в 18:00\n"
            "• завтра в 15:30\n"
            "• 31.12.2024 23:59\n"
            "• через 2 часа\n"
            "• 15:30",
            parse_mode="Markdown"
        )
        await state.set_state(TaskStates.waiting_for_deadline)
    
    await callback.answer()

# Обработка дедлайна
@dp.message(TaskStates.waiting_for_deadline)
async def process_deadline_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    deadline_text = message.text.strip()
    
    data = await state.get_data()
    task_text = data['task_text']
    
    deadline = parse_time(deadline_text)
    
    if not deadline:
        await message.answer(
            "❌ Не удалось распознать время.\n"
            "Попробуйте еще раз или введите /cancel для отмены.\n\n"
            "*Примеры:*\n"
            "• сегодня в 18:00\n"
            "• завтра в 15:30\n"
            "• 31.12.2024 23:59",
            parse_mode="Markdown"
        )
        return
    
    if user_id not in tasks_storage:
        tasks_storage[user_id] = []
    
    new_task = {
        'text': task_text,
        'completed': False,
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'completed_at': None,
        'deadline': deadline.isoformat(),
        'reminders': []
    }
    
    tasks_storage[user_id].append(new_task)
    save_data()
    
    deadline_formatted = format_time(deadline)
    await message.answer(
        f"✅ Задача добавлена: *{task_text}*\n"
        f"📅 Дедлайн: *{deadline_formatted}*",
        parse_mode="Markdown"
    )
    
    # Предлагаем установить напоминание
    task_index = len(tasks_storage[user_id]) - 1
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔔 Напоминание", callback_data=f"set_reminder_{task_index}"),
            InlineKeyboardButton(text="📋 Список задач", callback_data="show_all_tasks")
        ]
    ])
    
    await message.answer(
        "Хотите установить напоминание для этой задачи?",
        reply_markup=keyboard
    )
    
    await state.clear()

# Команда /list
@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    await show_task_list(message)

# Команда /deadlines
@dp.message(Command("deadlines"))
async def cmd_deadlines(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in tasks_storage or not tasks_storage[user_id]:
        await message.answer("📭 У вас нет задач с дедлайнами!")
        return
    
    tasks_with_deadlines = [task for task in tasks_storage[user_id] 
                           if task.get('deadline') and not task['completed']]
    
    if not tasks_with_deadlines:
        await message.answer("📭 Нет активных задач с дедлайнами!")
        return
    
    tasks_with_deadlines.sort(key=lambda x: datetime.fromisoformat(x['deadline']))
    
    list_text = "⏰ *Задачи с дедлайнами:*\n\n"
    
    for i, task in enumerate(tasks_with_deadlines, 1):
        deadline = datetime.fromisoformat(task['deadline'])
        deadline_str = format_deadline(task['deadline'])
        time_left = deadline - datetime.now()
        
        list_text += f"{i}. *{task['text']}*\n"
        list_text += f"   {deadline_str}\n"
        
        if time_left.days < 1 and time_left.seconds > 0:
            hours = time_left.seconds // 3600
            if hours > 0:
                list_text += f"   ⚠️ Осталось: {hours} час.\n"
            else:
                minutes = time_left.seconds // 60
                list_text += f"   ⚠️ Осталось: {minutes} мин.\n"
        
        list_text += "\n"
    
    await message.answer(list_text, parse_mode="Markdown")

# Команда /reminders
@dp.message(Command("reminders"))
async def cmd_reminders(message: types.Message):
    user_id = message.from_user.id
    
    user_reminders = [
        (reminder_id, reminder) 
        for reminder_id, reminder in reminders_storage.items()
        if reminder['user_id'] == user_id
    ]
    
    if not user_reminders:
        await message.answer("🔕 У вас нет активных напоминаний!")
        return
    
    list_text = "🔔 *Ваши напоминания:*\n\n"
    
    for reminder_id, reminder in user_reminders:
        try:
            reminder_time = datetime.fromisoformat(reminder['reminder_time'])
            time_left = reminder_time - datetime.now()
            
            list_text += f"• *{reminder['task_text']}*\n"
            list_text += f"  🕐 {format_time(reminder_time)}\n"
            
            if time_left.days > 0:
                list_text += f"  ⏳ Через {time_left.days} дней\n"
            elif time_left.seconds // 3600 > 0:
                list_text += f"  ⏳ Через {time_left.seconds // 3600} час.\n"
            elif time_left.seconds // 60 > 0:
                list_text += f"  ⏳ Через {time_left.seconds // 60} мин.\n"
            
            list_text += "\n"
        except Exception:
            continue
    
    # Кнопка для удаления напоминаний
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑️ Удалить все напоминания", callback_data="clear_all_reminders")
        ]
    ])
    
    await message.answer(list_text, parse_mode="Markdown", reply_markup=keyboard)

# Показать детали задачи
@dp.callback_query(F.data.startswith("view_task_"))
async def view_task_details(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    task_index = int(callback.data.split("_")[2])
    
    if user_id in tasks_storage and 0 <= task_index < len(tasks_storage[user_id]):
        task = tasks_storage[user_id][task_index]
        
        details_text = f"📋 *Детали задачи*\n\n"
        details_text += f"*Задача:* {task['text']}\n"
        details_text += f"*Статус:* {'✅ Выполнена' if task['completed'] else '⭕ В процессе'}\n"
        details_text += f"*Создана:* {task['created_at']}\n"
        
        if task.get('deadline'):
            deadline_str = format_deadline(task['deadline'])
            details_text += f"*Дедлайн:* {deadline_str}\n"
        
        if task.get('completed_at'):
            details_text += f"*Выполнена:* {task['completed_at']}\n"
        
        # Показываем напоминания для этой задачи
        task_reminders = [
            reminder for reminder_id, reminder in reminders_storage.items()
            if reminder['user_id'] == user_id and reminder['task_index'] == task_index
        ]
        
        if task_reminders:
            details_text += "\n*🔔 Напоминания:*\n"
            for reminder in task_reminders:
                reminder_time = datetime.fromisoformat(reminder['reminder_time'])
                details_text += f"• {format_time(reminder_time)}\n"
        
        keyboard = create_tasks_keyboard(user_id, task_index)
        await callback.message.edit_text(details_text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await callback.answer("Задача не найдена!")

# Установка дедлайна для существующей задачи
@dp.callback_query(F.data.startswith("set_deadline_"))
async def set_existing_deadline(callback: types.CallbackQuery, state: FSMContext):
    task_index = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    await state.update_data(task_index=task_index)
    
    await callback.message.edit_text(
        "📅 Введите новый дедлайн для задачи:\n\n"
        "*Примеры:*\n"
        "• сегодня в 18:00\n"
        "• завтра в 15:30\n"
        "• 31.12.2024 23:59\n"
        "• через 2 часа",
        parse_mode="Markdown"
    )
    
    await state.set_state(TaskStates.waiting_for_deadline_edit)
    await callback.answer()

# Обработка изменения дедлайна
@dp.message(TaskStates.waiting_for_deadline_edit)
async def process_deadline_edit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    deadline_text = message.text.strip()
    
    data = await state.get_data()
    task_index = data['task_index']
    
    if user_id in tasks_storage and 0 <= task_index < len(tasks_storage[user_id]):
        deadline = parse_time(deadline_text)
        
        if not deadline:
            await message.answer("❌ Не удалось распознать время. Попробуйте еще раз.")
            return
        
        tasks_storage[user_id][task_index]['deadline'] = deadline.isoformat()
        save_data()
        
        deadline_formatted = format_time(deadline)
        await message.answer(
            f"✅ Дедлайн обновлен!\n"
            f"Задача: *{tasks_storage[user_id][task_index]['text']}*\n"
            f"Новый дедлайн: *{deadline_formatted}*",
            parse_mode="Markdown"
        )
        
        # Предлагаем установить напоминание
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Напоминание", callback_data=f"set_reminder_{task_index}"),
                InlineKeyboardButton(text="📋 Список задач", callback_data="show_all_tasks")
            ]
        ])
        
        await message.answer(
            "Хотите установить напоминание для этой задачи?",
            reply_markup=keyboard
        )
    
    await state.clear()

# Установка напоминания
@dp.callback_query(F.data.startswith("set_reminder_"))
async def set_reminder(callback: types.CallbackQuery, state: FSMContext):
    task_index = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    if user_id in tasks_storage and 0 <= task_index < len(tasks_storage[user_id]):
        task = tasks_storage[user_id][task_index]
        
        await state.update_data(task_index=task_index, task_text=task['text'])
        
        await callback.message.edit_text(
            "🔔 Введите время напоминания:\n\n"
            "*Примеры:*\n"
            "• через 30 минут\n"
            "• через 2 часа\n"
            "• сегодня в 18:00\n"
            "• завтра в 10:00\n\n"
            "Напоминание придет за 30 минут до дедлайна (если установлен), "
            "или в указанное вами время.",
            parse_mode="Markdown"
        )
        
        await state.set_state(TaskStates.waiting_for_reminder)
    
    await callback.answer()

# Обработка напоминания
@dp.message(TaskStates.waiting_for_reminder)
async def process_reminder_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    reminder_text = message.text.strip()
    
    data = await state.get_data()
    task_index = data['task_index']
    task_text = data['task_text']
    
    if user_id in tasks_storage and 0 <= task_index < len(tasks_storage[user_id]):
        reminder_time = parse_time(reminder_text)
        
        # Если не указано явное время, используем дедлайн минус 30 минут
        if not reminder_time and tasks_storage[user_id][task_index].get('deadline'):
            deadline = datetime.fromisoformat(tasks_storage[user_id][task_index]['deadline'])
            reminder_time = deadline - timedelta(minutes=30)
        
        if not reminder_time:
            await message.answer("❌ Не удалось распознать время. Попробуйте еще раз.")
            return
        
        # Создаем напоминание
        reminder_id = create_reminder(user_id, task_index, reminder_time, task_text)
        
        await message.answer(
            f"🔔 Напоминание установлено!\n"
            f"Задача: *{task_text}*\n"
            f"Время: *{format_time(reminder_time)}*",
            parse_mode="Markdown"
        )
    
    await state.clear()

# Удаление всех напоминаний
@dp.callback_query(F.data == "clear_all_reminders")
async def clear_all_reminders(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Находим все напоминания пользователя
    user_reminder_ids = [
        reminder_id for reminder_id, reminder in reminders_storage.items()
        if reminder['user_id'] == user_id
    ]
    
    # Удаляем из планировщика
    for reminder_id in user_reminder_ids:
        try:
            scheduler.remove_job(reminder_id)
        except Exception:
            pass
        
        if reminder_id in reminders_storage:
            del reminders_storage[reminder_id]
    
    save_data()
    
    await callback.message.edit_text("✅ Все напоминания удалены!")
    await callback.answer()

# Показать все задачи
@dp.callback_query(F.data == "show_all_tasks")
async def show_all_tasks_callback(callback: types.CallbackQuery):
    await show_task_list(callback.message)
    await callback.answer()

# Функция для показа списка задач
async def show_task_list(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in tasks_storage or not tasks_storage[user_id]:
        await message.answer("📭 Ваш список задач пуст!\nОтправьте мне текст, чтобы добавить первую задачу.")
        return
    
    tasks = tasks_storage[user_id]
    
    # Разделяем задачи на выполненные и активные
    active_tasks = [task for task in tasks if not task['completed']]
    completed_tasks = [task for task in tasks if task['completed']]
    
    list_text = f"📋 *Ваши задачи*\n\n"
    
    if active_tasks:
        list_text += f"*Активные ({len(active_tasks)}):*\n"
        for i, task in enumerate(active_tasks, 1):
            icon = "⏰" if task.get('deadline') else "📝"
            deadline_str = ""
            
            if task.get('deadline'):
                deadline_str = f" - {format_deadline(task['deadline'])}"
            
            list_text += f"{i}. {icon} {task['text'][:40]}{deadline_str}\n"
    
    if completed_tasks:
        list_text += f"\n*✅ Выполненные ({len(completed_tasks)}):*\n"
        for i, task in enumerate(completed_tasks, 1):
            list_text += f"{i}. ✅ {task['text'][:40]}\n"
    
    keyboard = create_tasks_keyboard(user_id)
    await message.answer(list_text, parse_mode="Markdown", reply_markup=keyboard)

# Обработка нажатия на задачу (отметка выполнения)
@dp.callback_query(F.data.startswith("task_"))
async def process_task_click(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    task_index = int(callback.data.split("_")[1])
    
    if user_id in tasks_storage and 0 <= task_index < len(tasks_storage[user_id]):
        task = tasks_storage[user_id][task_index]
        
        # Меняем статус задачи
        task['completed'] = not task['completed']
        
        if task['completed']:
            task['completed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Удаляем напоминания для выполненной задачи
            reminder_ids = [
                reminder_id for reminder_id, reminder in reminders_storage.items()
                if reminder['user_id'] == user_id and reminder['task_index'] == task_index
            ]
            
            for reminder_id in reminder_ids:
                try:
                    scheduler.remove_job(reminder_id)
                except Exception:
                    pass
                
                if reminder_id in reminders_storage:
                    del reminders_storage[reminder_id]
            
            save_data()
        else:
            task['completed_at'] = None
        
        save_data()
        
        await callback.answer(f"Задача отмечена как {'выполненная' if task['completed'] else 'невыполненная'}!")
        
        # Обновляем список
        await show_task_list(callback.message)
    else:
        await callback.answer("Задача не найдена!")

# Обработка кнопки "Добавить задачу"
@dp.callback_query(F.data == "add_task")
async def process_add_task(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Введите текст новой задачи:")
    await state.set_state(TaskStates.waiting_for_task)
    await callback.answer()

# Обработка кнопки "Очистить выполненные"
@dp.callback_query(F.data == "clear_completed")
async def process_clear_completed(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id in tasks_storage:
        # Удаляем только выполненные задачи
        initial_count = len(tasks_storage[user_id])
        tasks_storage[user_id] = [task for task in tasks_storage[user_id] if not task['completed']]
        removed_count = initial_count - len(tasks_storage[user_id])
