# config.py

import json
import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env (для скрытия токена и ID на GitHub)
load_dotenv() 

# --- ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ И КОНСТАНТЫ ---

# Здесь мы будем хранить объявления, ожидающие модерации. 
AD_PENDING_STORAGE = {} 

# Хранилище для опубликованных постов, которые пользователь может удалить
# {user_id: [ {'msg_id': list[int], 'description': str, 'topic_id': int}, ... ]}
AD_PUBLISHED_STORAGE = {} 

# --- ПЕРСИСТЕНТНОСТЬ (JSON ФАЙЛЫ) ---
PUBLISHED_DATA_FILE = 'published_posts.json'

# !!! ВСТАВЬТЕ СВОИ ДАННЫЕ СЮДА !!!
# Токен бота берется из переменной окружения TELEGRAM_BOT_TOKEN в файле .env
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") 

# НОВЫЕ ИЗМЕНЕНИЯ: Загружаем ID чатов/каналов из .env и преобразуем в int
# ID Вашей приватной группы (модерация)
MODERATION_CHAT_ID = int(os.getenv("MODERATION_CHAT_ID")) 
# ID целевого маркетплейса
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID")) 
# !!! КОНЕЦ ВСТАВКИ !!!

WATERMARK_TEXT = "Базар Варшава 🛍️" # Текст водяного знака
MAX_PHOTOS = 10 # Максимальное количество фото

# --- НАСТРОЙКИ ВЕТОК (TOPICS) ---

# Спец. ветки для "Куплю" и "Отдам даром"
TOPIC_BUY = 676   # Куплю
TOPIC_GIVE = 678  # Отдам даром

# Ветки для категорий (Продам)
# Ключи (слева) должны совпадать с callback_data в keyboards.py (без "cat_")
CATEGORY_TOPICS = {
    "auto": 659,          # Автомобили•Запчасти
    "bicycle": 680,       # Велосипеды•Самокаты
    "phones": 667,        # Смартфоны•Планшеты
    "other": 684,         # Другое
    "animals": 681,       # Животные
    "home": 677,          # Дом•Огород
    "sport": 675,         # Спорт•Хобби
    "electronics": 673,   # Вся электроника
    "consoles": 666,      # Консоли
    "computers": 665,     # Компьютеры
    "kids": 664,          # Товары для детей
    "men_clothes": 661,   # Мужская одежда
    "women_clothes": 660  # Женская одежда
}


# --- ФУНКЦИИ ПЕРСИСТЕНТНОСТИ ---

def load_data():
    """Загружает данные из JSON-файла при запуске."""
    global AD_PUBLISHED_STORAGE
    
    if os.path.exists(PUBLISHED_DATA_FILE):
        try:
            with open(PUBLISHED_DATA_FILE, 'r', encoding='utf-8') as f:
                # Ключи в JSON - это всегда строки, поэтому преобразуем user_id обратно в int
                loaded_data = json.load(f)
                AD_PUBLISHED_STORAGE = {int(k): v for k, v in loaded_data.items()}
                print(f"Загружено {len(AD_PUBLISHED_STORAGE)} записей опубликованных постов.")
        except Exception as e:
            print(f"Ошибка загрузки опубликованных данных: {e}")
            
def save_data():
    """Сохраняет текущие данные в JSON-файл перед выключением."""
    global AD_PUBLISHED_STORAGE
    try:
        with open(PUBLISHED_DATA_FILE, 'w', encoding='utf-8') as f:
            # Преобразуем user_id (int) в строку для корректной сериализации в JSON
            json_compatible_data = {str(k): v for k, v in AD_PUBLISHED_STORAGE.items()}
            json.dump(json_compatible_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка сохранения опубликованных данных: {e}")