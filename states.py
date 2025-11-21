# states.py

from aiogram.fsm.state import State, StatesGroup

# --- МАШИНА СОСТОЯНИЙ (FSM) ---
class AdSteps(StatesGroup):
    # Основные шаги подачи объявления
    choosing_category = State()      # Выбор категории
    awaiting_photo_or_skip = State() # Ожидание первого фото или пропуска
    entering_desc = State()          # Ввод описания
    entering_contact = State()       # Ввод контактов
    awaiting_final_action = State()  # Этап превью
    
    # Шаги для удаления поста
    awaiting_post_to_delete = State()        # Ожидание выбора поста из списка
    awaiting_delete_confirmation = State()   # Ожидание подтверждения удаления