# utils.py

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont 
import logging

# --- КОНСТАНТЫ ВОТЕРМАРКА ---
WATERMARK_TEXT = "Базар Варшава" # <-- ИСПОЛЬЗУЙТЕ СВОЙ ТЕКСТ ЗДЕСЬ
WATERMARK_OPACITY = 120 # Прозрачность вотермарка (0-255). 120 - средняя видимость.
# ВАЖНО: ДЛЯ КИРИЛЛИЦЫ НУЖЕН TTF ШРИФТ. Укажите путь к нему.
FONT_PATH = "assets/Roboto.ttf" # <-- ИЗМЕНИТЬ НА ВАШ ПУТЬ И ИМЯ ФАЙЛА 

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
        img = img.convert("RGBA") # Преобразуем для работы с прозрачностью
    except Exception as e:
        # Если не удалось открыть изображение, возвращаем исходный (необработанный) буфер
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
        if FONT_PATH:
            # Используем TrueType шрифт (требуется для кириллицы)
            font = ImageFont.truetype(FONT_PATH, font_size) 
        else:
            # Используем шрифт по умолчанию (может не поддерживать кириллицу)
            font = ImageFont.load_default(size=font_size) 
    except (IOError, OSError):
        # Fallback, если TrueType шрифт не найден или путь неверный
        font = ImageFont.load_default(size=font_size)
        
    # Рассчет положения текста (правый нижний угол с отступами)
    padding_x = int(width * 0.02) # 2% от ширины
    padding_y = int(height * 0.02) # 2% от высоты
    
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
    img = img.convert("RGB") # Удаляем альфа-канал перед сохранением в JPEG
    img.save(output_buffer, format="JPEG", quality=90) 
    
    # ГАРАНТИЯ: Сброс курсора в начало буфера перед возвратом
    output_buffer.seek(0)
    
    return output_buffer