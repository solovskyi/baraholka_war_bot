# utils.py

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont 
import logging
import os # <-- ДОДАНО ДЛЯ РОБОТИ З АБСОЛЮТНИМИ ШЛЯХАМИ

# --- КОНСТАНТЫ ВОТЕРМАРКА ---
WATERMARK_TEXT = "Базар Варшава" 
WATERMARK_OPACITY = 120 

# --- ОПРЕДЕЛЕНИЕ АБСОЛЮТНОГО ПУТИ К ШРИФТУ ---
# 1. Получаем путь к текущему файлу (utils.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Строим полный путь: /home/USERNAME/baraholka_war_bot/assets/Roboto.ttf
FONT_PATH = os.path.join(BASE_DIR, "assets", "Roboto.ttf")

# --- ПРОВЕРКА ДЛЯ ЛОГГИРОВАНИЯ (Необязательно, но полезно) ---
if not os.path.exists(FONT_PATH):
    logging.warning(f"Шрифт не найден по пути: {FONT_PATH}")

async def apply_watermark(bot, file_id):
    """
    Применяет вотермарк к изображению, полученному по file_id.
    Возвращает объект io.BytesIO с изображением в формате JPEG.
    """
    
    # 1. Загрузка файла
    try:
        file = await bot.get_file(file_id)
    except Exception as e:
        logging.error(f"Ошибка получения файла: {e}")
        return BytesIO()
        
    # Загружаем файл в байтовый буфер
    photo_buffer = BytesIO()
    await bot.download_file(file.file_path, photo_buffer)
    photo_buffer.seek(0)
    
    # 2. Открытие изображения
    try:
        img = Image.open(photo_buffer)
        img = img.convert("RGBA")
    except Exception as e:
        logging.error(f"Ошибка открытия изображения: {e}")
        photo_buffer.seek(0) 
        return photo_buffer

    # 3. Настройка и применение вотермарка
    width, height = img.size
    
    # Создаем прозрачное наложение
    watermark_layer = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark_layer)
    
    # ВЫБОР РАЗМЕРА ШРИФТА: 1/12
    font_size = int(width / 12) 
    if font_size < 20: 
        font_size = 20
        
    try:
        # Теперь FONT_PATH всегда является абсолютным путем
        font = ImageFont.truetype(FONT_PATH, font_size) 
    except (IOError, OSError) as e:
        # Fallback, если TrueType шрифт не найден или путь неверный
        logging.error(f"Ошибка загрузки TrueType шрифта: {e}. Используется шрифт по умолчанию.")
        font = ImageFont.load_default(size=font_size)
        
    # Рассчет положения текста (правый нижний угол с отступами)
    padding_x = int(width * 0.02)
    padding_y = int(height * 0.02)
    
    x = width - padding_x
    y = height - padding_y
    
    # Настройки цвета и прозрачности (RGBA)
    text_color = (255, 255, 255, WATERMARK_OPACITY) 
    
    # Отрисовка текста
    draw.text((x, y), WATERMARK_TEXT, font=font, fill=text_color, anchor="rb")
    
    # Наложение вотермарка на изображение
    img = Image.alpha_composite(img, watermark_layer)
    
    # 4. Сохранение результата в новый буфер
    output_buffer = BytesIO()
    
    # Сохраняем в JPEG для совместимости с MediaGroup и уменьшения размера
    img = img.convert("RGB")
    img.save(output_buffer, format="JPEG", quality=90) 
    
    output_buffer.seek(0)
    
    return output_buffer