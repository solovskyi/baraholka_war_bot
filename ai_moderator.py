# ai_moderator.py

import logging
import json
import io
from PIL import Image # Библиотека для обработки изображений
import google.generativeai as genai
from config import GOOGLE_API_KEY

# 1. Настройка Google Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# 2. Описываем правила для ИИ (Системная инструкция)
SYSTEM_PROMPT = """
Ты — строгий модератор доски объявлений в Telegram "Базар Варшава".
Твоя задача: проанализировать текст, фото и категорию.

ПРАВИЛА:
1. ЗАПРЕЩЕНО: Наркотики, оружие, проституция, мошенничество, спам, лекарства.
2. КАТЕГОРИЯ: Объявление должно соответствовать тематике категории (включая аксессуары и запчасти).
   - Если категория "Животные", а продают поводок или корм — это OK (APPROVE).
   - Если категория "Животные", а на фото машина — это REJECT.
3. ТОВАР vs УСЛУГА: 
   - Раздел "Продать" предназначен ТОЛЬКО для физических товаров.
   - Любые УСЛУГИ (ремонт, аренда, работа, маникюр, перевозки) -> REJECT.
   - Причина отказа для услуг: "Реклама услуг платная. Напишите админу."
4. ФОТО: Должно соответствовать описанию.
5. ОПИСАНИЕ: Должно быть понятным.

Верни ответ ТОЛЬКО в формате JSON:
{
    "decision": "approve" или "reject" или "manual",
    "reason": "Краткая причина твоего решения на русском языке."
}

Используй "approve", если это ТОВАР, категория подходит и нет запрещенки.
"""

# 3. Создаем модель
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction=SYSTEM_PROMPT,
    generation_config={"response_mime_type": "application/json"} 
)

async def moderate_ad_with_ai(bot, ad_data: dict) -> dict:
    """
    Функция получает данные объявления, скачивает фото и спрашивает мнение у Gemini.
    """
    description = ad_data.get('description', 'Нет описания')
    cat_code = ad_data.get('category', 'Не указана')
    
    # 🔥 РАСШИРЕННЫЕ ОПИСАНИЯ КАТЕГОРИЙ 🔥
    # Теперь ИИ понимает, что входит в каждую категорию
    CAT_NAMES = {
        "auto": "Автомобили, мотоциклы, запчасти, шины, диски, автохимия, аксессуары для авто",
        "bicycle": "Велосипеды, самокаты, гироскутеры, экипировка, запчасти к ним",
        "phones": "Смартфоны, телефоны, чехлы, зарядки, кабеля, повербанки, запчасти, держатели",
        "computers": "Компьютеры, ноутбуки, видеокарты, мониторы, клавиатуры, мышки, принтеры, комплектующие",
        "consoles": "Игровые консоли (PlayStation, Xbox, Nintendo), диски с играми, геймпады, рули, аксессуары",
        "electronics": "Любая электроника: фотокамеры, наушники, колонки, телевизоры, умные часы, вейпы (если разрешено), бытовая техника",
        "home": "Все для дома: мебель, посуда, текстиль, декор, инструменты, стройматериалы, товары для сада",
        "animals": "Животные, корм, клетки, переноски, игрушки для животных, поводки, лотки",
        "sport": "Спортивный инвентарь, тренажеры, музыкальные инструменты, настольные игры, товары для хобби и творчества",
        "men_clothes": "Мужская одежда, обувь, сумки, рюкзаки, часы, аксессуары",
        "women_clothes": "Женская одежда, обувь, сумки, украшения, косметика, аксессуары",
        "kids": "Детская одежда, игрушки, коляски, автокресла, детская мебель, подгузники",
        "other": "Книги, канцелярия, билеты и всё остальное, что не подошло в другие категории"
    }
    
    category_desc = CAT_NAMES.get(cat_code, cat_code)
    
    ad_type = ad_data.get('ad_type', 'sell')
    photo_ids = ad_data.get('photos', [])

    # Формируем запрос
    user_prompt = f"""
    Выбранная категория (что в неё входит): {category_desc}
    Тип объявления: {ad_type}
    Описание пользователя: {description}
    """
    
    content_parts = [user_prompt] 

    if photo_ids:
        try:
            first_photo_id = photo_ids[0]
            file = await bot.get_file(first_photo_id)
            file_bytes = io.BytesIO()
            await bot.download_file(file.file_path, file_bytes)
            image = Image.open(file_bytes)
            content_parts.append(image)
        except Exception as e:
            logging.error(f"AI: Не удалось загрузить фото: {e}")

    try:
        logging.info("⏳ Отправка запроса к Gemini...")
        response = await model.generate_content_async(content_parts)
        result_json = json.loads(response.text)
        logging.info(f"🤖 AI Вердикт: {result_json}")
        return result_json

    except Exception as e:
        logging.error(f"AI Error: {e}")
        return {"decision": "manual", "reason": "Ошибка подключения к ИИ"}