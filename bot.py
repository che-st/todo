import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv('BOT_TOKEN'))
dp = Dispatcher()

# Хранилище задач (в реальном проекте используйте базу данных)
# Структура: user_id -> список задач
tasks_storage: Dict[int, List[Dict]] = {}

# Файл для сохранения данных
DATA_FILE = "tasks_data.json"

# Состояния FSM
class TaskStates(StatesGroup):
    waiting_for_task = State()
    waiting_for_task_edit = State()

# Загрузка данных из файла
def load_data():
    global tasks_storage
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            tasks_storage = json.load(f)
            # Преобразуем ключи обратно в int (JSON сохраняет их как строки)
            tasks_storage = {int(k): v for k, v in tasks_storage.items()}
    except (FileNotFoundError, json.JSONDecodeError):
        tasks_storage = {}

# Сохранение данных в файл
def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks_storage, f, ensure_ascii=False, indent=2)

# Функция для создания клавиатуры с задачами
def create_tasks_keyboard(user_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if user_id in tasks_storage and tasks_storage[user_id]:
        for i, task in enumerate(tasks_storage[user_id]):
            status = "✅" if task['completed'] else "⭕"
            button_text = f"{status} {task['text'][:30]}"
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"task_{i}"
                )
            ])
    
    # Кнопки действий
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add_task"),
        InlineKeyboardButton(text="🗑️ Очистить выполненные", callback_data="clear_completed")
    ])
    
    return keyboard

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    # Инициализируем список задач для пользователя, если его нет
    if user_id not in tasks_storage:
        tasks_storage[user_id] = []
        save_data()
    
    welcome_text = (
        "📝 *To-Do List Bot*\n\n"
        "Доступные команды:\n"
        "/start - Начать работу\n"
        "/add - Добавить новую задачу\n"
        "/list - Показать список задач\n"
        "/help - Помощь\n\n"
        "Просто отправьте мне текст задачи, и я добавлю её в список!"
    )
    
    await message.answer(welcome_text, parse_mode="Markdown")

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 *Помощь*\n\n"
        "*Как пользоваться ботом:*\n"
        "1. Отправьте текст задачи, чтобы добавить её\n"
        "2. Используйте /list для просмотра всех задач\n"
        "3. Нажмите на задачу в списке, чтобы отметить её выполненной/невыполненной\n"
        "4. Используйте кнопки под списком для управления\n\n"
        "*Команды:*\n"
        "/start - Начало работы\n"
        "/add - Добавить задачу\n"
        "/list - Показать задачи\n"
        "/help - Эта справка"
    )
    await message.answer(help_text, parse_mode="Markdown")

# Команда /add
@dp.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
    await message.answer("📝 Введите текст новой задачи:")
    await state.set_state(TaskStates.waiting_for_task)

# Обработка текста для добавления задачи
@dp.message(TaskStates.waiting_for_task)
async def process_task_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    task_text = message.text.strip()
    
    if not task_text:
        await message.answer("❌ Текст задачи не может быть пустым!")
        return
    
    # Инициализируем список задач для пользователя, если его нет
    if user_id not in tasks_storage:
        tasks_storage[user_id] = []
    
    # Добавляем новую задачу
    new_task = {
        'text': task_text,
        'completed': False,
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'completed_at': None
    }
    
    tasks_storage[user_id].append(new_task)
    save_data()
    
    await message.answer(f"✅ Задача добавлена: *{task_text}*", parse_mode="Markdown")
    await state.clear()
    
    # Показываем обновленный список
    await show_task_list(message)

# Команда /list
@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    await show_task_list(message)

# Функция для показа списка задач
async def show_task_list(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in tasks_storage or not tasks_storage[user_id]:
        await message.answer("📭 Ваш список задач пуст!\nОтправьте мне текст, чтобы добавить первую задачу.")
        return
    
    tasks = tasks_storage[user_id]
    completed_count = sum(1 for task in tasks if task['completed'])
    
    list_text = f"📋 *Ваши задачи* ({completed_count}/{len(tasks)} выполнено)\n\n"
    
    for i, task in enumerate(tasks, 1):
        status = "✅" if task['completed'] else "⭕"
        list_text += f"{i}. {status} {task['text']}\n"
        if task['completed'] and task['completed_at']:
            list_text += f"   🕐 Выполнено: {task['completed_at']}\n"
    
    keyboard = create_tasks_keyboard(user_id)
    await message.answer(list_text, parse_mode="Markdown", reply_markup=keyboard)

# Обработка нажатия на задачу
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
        else:
            task['completed_at'] = None
        
        save_data()
        
        # Обновляем сообщение
        tasks = tasks_storage[user_id]
        completed_count = sum(1 for task in tasks if task['completed'])
        
        list_text = f"📋 *Ваши задачи* ({completed_count}/{len(tasks)} выполнено)\n\n"
        
        for i, task in enumerate(tasks, 1):
            status = "✅" if task['completed'] else "⭕"
            list_text += f"{i}. {status} {task['text']}\n"
            if task['completed'] and task['completed_at']:
                list_text += f"   🕐 Выполнено: {task['completed_at']}\n"
        
        keyboard = create_tasks_keyboard(user_id)
        await callback.message.edit_text(list_text, parse_mode="Markdown", reply_markup=keyboard)
        await callback.answer(f"Задача отмечена как {'выполненная' if task['completed'] else 'невыполненная'}!")
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
        
        save_data()
        
        if removed_count > 0:
            await callback.answer(f"Удалено {removed_count} выполненных задач!")
        else:
            await callback.answer("Нет выполненных задач для удаления!")
        
        # Обновляем список
        await show_task_list(callback.message)
    else:
        await callback.answer("Список задач пуст!")

# Обработка обычных сообщений (добавление задачи без команды)
@dp.message()
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    task_text = message.text.strip()
    
    if not task_text:
        return
    
    # Инициализируем список задач для пользователя, если его нет
    if user_id not in tasks_storage:
        tasks_storage[user_id] = []
    
    # Добавляем новую задачу
    new_task = {
        'text': task_text,
        'completed': False,
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'completed_at': None
    }
    
    tasks_storage[user_id].append(new_task)
    save_data()
    
    await message.answer(f"✅ Задача добавлена: *{task_text}*", parse_mode="Markdown")
    await show_task_list(message)

# Главная функция
async def main():
    # Загружаем данные при старте
    load_data()
    
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
