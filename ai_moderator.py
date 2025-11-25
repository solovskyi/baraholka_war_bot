# ai_moderator.py

import logging
import json
import io
from PIL import Image 
import google.generativeai as genai
from config import GOOGLE_API_KEY

genai.configure(api_key=GOOGLE_API_KEY)

# 👇 ДОДАНО ПРАВИЛО №6 ПРО ТЕКСТ 👇
SYSTEM_PROMPT = """
Ты — строгий модератор доски объявлений в Telegram "Базар Варшава".
Твоя задача: проанализировать текст, фото и категорию.

ПРАВИЛА:
1. ЗАПРЕЩЕНО: Наркотики, оружие, проституция, мошенничество, спам, лекарства.
2. КАТЕГОРИЯ: Объявление должно соответствовать тематике.
3. ТОВАР vs УСЛУГА: Раздел "Продать" ТОЛЬКО для физических товаров. Услуги -> REJECT.

4. АНАЛИЗ ФОТО:
   - Отличай РЕАЛЬНЫЙ ОБЪЕКТ от ИЗОБРАЖЕНИЯ на экране.
   - Если категория "Авто", а на фото телефон, на экране которого машина -> REJECT.
   - Скриншоты из игр или фото с мониторов -> REJECT (или MANUAL).

5. СООТВЕТСТВИЕ:
   - Если категория "Животные", а продают корм -> APPROVE.
   - Если категория "Животные", а на фото машина -> REJECT.

6. КАЧЕСТВО ТЕКСТА (АНТИ-СПАМ):
   - Если описание состоит из бессмысленного набора букв (например: "фывфыв", "asdfg", "kjhgfd", "11111"), только из смайликов или не несет смысла -> REJECT.
   - Причина: "Описание неинформативно."

Верни ответ ТОЛЬКО в формате JSON:
{
    "decision": "approve" или "reject" или "manual",
    "reason": "Краткая причина твоего решения на русском языке."
}

Используй "approve", если это реальный товар, понятный текст и верная категория.
"""

model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction=SYSTEM_PROMPT,
    generation_config={"response_mime_type": "application/json"} 
)

async def moderate_ad_with_ai(bot, ad_data: dict) -> dict:
    description = ad_data.get('description', 'Нет описания')
    cat_code = ad_data.get('category', 'Не указана')
    
    # Расшифровка категорий
    CAT_NAMES = {
        "auto": "Автомобили, мотоциклы, запчасти, шины, диски, автохимия",
        "bicycle": "Велосипеды, самокаты, гироскутеры, экипировка",
        "phones": "Смартфоны, телефоны, чехлы, зарядки, повербанки",
        "computers": "Компьютеры, ноутбуки, комплектующие, периферия",
        "consoles": "Игровые консоли, диски с играми, геймпады",
        "electronics": "Фотокамеры, аудио, ТВ, бытовая техника, вейпы",
        "home": "Мебель, посуда, текстиль, инструмент, стройматериалы",
        "animals": "Животные, корм, клетки, аксессуары для животных",
        "sport": "Спорт инвентарь, хобби, музыкальные инструменты",
        "men_clothes": "Мужская одежда, обувь, аксессуары",
        "women_clothes": "Женская одежда, обувь, аксессуары",
        "kids": "Детская одежда, игрушки, коляски",
        "other": "Книги, канцелярия, билеты, другое"
    }
    
    category_desc = CAT_NAMES.get(cat_code, cat_code)
    ad_type = ad_data.get('ad_type', 'sell')
    photo_ids = ad_data.get('photos', [])

    user_prompt = f"""
    Выбранная категория: {category_desc}
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