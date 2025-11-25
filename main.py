# main.py

import asyncio
import logging
import time
from typing import Union, Tuple, List

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InputMediaPhoto, Message, BufferedInputFile, CallbackQuery, 
    InlineKeyboardMarkup, InlineKeyboardButton 
)

# --- ИМПОРТ ---
from config import (
    TOKEN, MODERATION_CHAT_ID, TARGET_CHANNEL_ID, MAX_PHOTOS, AD_PENDING_STORAGE,
    CATEGORY_TOPICS, TOPIC_BUY, TOPIC_GIVE, 
    AD_PUBLISHED_STORAGE, # Хранилище опубликованных постов
    load_data, # Функция для загрузки данных
    save_data  # Функция для сохранения данных
)
from states import AdSteps 
from keyboards import (
    main_menu_keyboard, category_keyboard, photo_step_keyboard, 
    skip_contact_keyboard, final_preview_keyboard,
    get_moderation_keyboard, main_menu_return_keyboard,
    adv_contact_keyboard,
    get_user_posts_keyboard, 
    get_delete_confirmation_keyboard 
)
from utils import apply_watermark 

# 🔥 ИМПОРТ ДЛЯ ИИ 🔥
from ai_moderator import moderate_ad_with_ai

# --- НАСТРОЙКИ ---
logging.basicConfig(level=logging.INFO) 
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def delete_previous_messages(chat_id: int, state: FSMContext):
    """Удаляет старые сообщения, чтобы очистить чат."""
    data = await state.get_data()
    
    keys_to_delete = [
        'main_menu_message_id',
        'category_menu_id',
        'photo_status_message_id',
        'description_message_id',
        'contact_message_id',
        'description_error_id'
    ]
    
    for key in keys_to_delete:
        msg_id = data.get(key)
        if msg_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    preview_ids = data.get('preview_message_ids', [])
    for msg_id in preview_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

    await state.update_data({key: None for key in keys_to_delete})
    await state.update_data(preview_message_ids=[])


def get_ad_text(data: dict) -> str:
    """Формирует текст объявления для превью и публикации."""
    ad_type = data.get('ad_type', 'sell')
    description = data.get('description', '')
    contact_info = data.get('contact')
    
    prefix = ""
    if ad_type == 'buy':
        prefix = "🛒 #КУПЛЮ\n\n"
    elif ad_type == 'give':
        prefix = "🎁 #ОТДАМ_ДАРОМ\n\n"
    
    contact_line = f"\n\n📞 {contact_info}" if contact_info and contact_info.strip() else ""
    
    return f"{prefix}{description}{contact_line}"


async def show_final_preview(message: types.Message, state: FSMContext):
    """Показывает финальный предпросмотр объявления пользователю."""
    data = await state.get_data()
    caption = get_ad_text(data)
    sent_preview_messages = []

    # 1. Отправляем заголовок
    title_msg = await message.answer("✨ ПРЕДПРОСМОТР ОБЪЯВЛЕНИЯ ✨", parse_mode="HTML")
    sent_preview_messages.append(title_msg)

    # --- ОБРАБОТКА ФОТО И ВОТЕРМАРК ---
    photo_ids = data.get('photos', [])
    content_sent = False
    
    if photo_ids:
        try:
            media_group = []
            for i, photo_id in enumerate(photo_ids):
                watermarked_photo_data = await apply_watermark(bot, photo_id) 
                watermarked_photo_data.seek(0)
                photo_file = BufferedInputFile(watermarked_photo_data.read(), filename=f"ad_wm_{i}.jpg")
                
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_file, caption=caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo_file))
            
            msgs = await message.answer_media_group(media=media_group)
            sent_preview_messages.extend(msgs)
            content_sent = True
            
        except Exception as e:
            logging.error(f"Preview MediaGroup failed for ad type {data.get('ad_type')}: {e}")
        
    if not content_sent:
        text_msg = await message.answer(caption, parse_mode="HTML")
        sent_preview_messages.append(text_msg)

    button_msg = await message.answer(
        "Выберите, что делать дальше:",
        reply_markup=final_preview_keyboard
    )
    sent_preview_messages.append(button_msg)
    
    preview_ids = [m.message_id for m in sent_preview_messages]
    await state.update_data(preview_message_ids=preview_ids)
    await state.set_state(AdSteps.awaiting_final_action)


async def clear_preview_messages(chat_id: int, state: FSMContext):
    """Удаляет сообщения предпросмотра."""
    data = await state.get_data()
    preview_ids = data.get('preview_message_ids', [])
    for msg_id in preview_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
    await state.update_data(preview_message_ids=[])


# --- 🔥 НОВАЯ ФУНКЦИЯ: УНИВЕРСАЛЬНАЯ ПУБЛИКАЦИЯ 🔥 ---
async def publish_post_to_channel(bot: Bot, ad_data: dict) -> Tuple[bool, Union[List[int], str]]:
    """
    Публикует пост в канал (вызывается и при авто-публикации, и модератором).
    Возвращает (Успех: bool, Результат: список ID сообщений или текст ошибки).
    """
    ad_type = ad_data.get('ad_type')
    category_code = ad_data.get('category')
    
    # Определяем тему (Topic)
    topic_id = None
    if ad_type == 'buy':
        topic_id = TOPIC_BUY
    elif ad_type == 'give':
        topic_id = TOPIC_GIVE
    else:
        topic_id = CATEGORY_TOPICS.get(category_code)

    final_caption = get_ad_text(ad_data)
    
    # Добавляем автора
    user_id = ad_data.get('user_id')
    try:
        user_info = await bot.get_chat(chat_id=user_id)
        author_identifier = user_info.username or user_info.id
        author_line = f"\n\n👤 @{author_identifier}"
        final_caption += author_line
    except Exception as e:
        logging.error(f"Failed to fetch user info for ID {user_id}: {e}")
        pass
    
    photo_ids = ad_data.get('photos', [])
    sent_message_ids = [] 

    try:
        if photo_ids:
            media_group = []
            for i, photo_id in enumerate(photo_ids):
                watermarked_photo_data = await apply_watermark(bot, photo_id)
                watermarked_photo_data.seek(0) 
                photo_file = BufferedInputFile(watermarked_photo_data.read(), filename=f"final_wm_{i}.jpg")
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_file, caption=final_caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo_file))
            
            msgs = await bot.send_media_group(chat_id=TARGET_CHANNEL_ID, media=media_group, message_thread_id=topic_id)
            for msg in msgs: sent_message_ids.append(msg.message_id)

        else:
            sent_msg = await bot.send_message(chat_id=TARGET_CHANNEL_ID, text=final_caption, parse_mode="HTML", message_thread_id=topic_id)
            sent_message_ids.append(sent_msg.message_id)
        
        # Сохраняем в базу опубликованных
        post_data = {
            'msg_id': sent_message_ids, 
            'description': final_caption,
            'topic_id': topic_id,
        }
        user_id_int = ad_data['user_id']
        if user_id_int not in AD_PUBLISHED_STORAGE:
            AD_PUBLISHED_STORAGE[user_id_int] = []
        AD_PUBLISHED_STORAGE[user_id_int].append(post_data)
        
        save_data()
        
        return True, sent_message_ids

    except Exception as e:
        logging.error(f"ERROR publishing: {e}")
        return False, str(e)


# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
@dp.callback_query(F.data == "start")
async def cmd_start_or_callback(callback_or_message: types.CallbackQuery | types.Message, state: FSMContext):
    """Обрабатывает команду /start или колбэк 'start' и выводит главное меню."""
    if isinstance(callback_or_message, types.CallbackQuery):
        message = callback_or_message.message
        await callback_or_message.answer()
        try: await callback_or_message.message.delete()
        except: pass
    else:
        message = callback_or_message

    await state.clear() 
    
    welcome_text = (
        "🏠 Главное меню\n\n"
        "🎯 Этот бот служит для публикации и удаления ваших объявлений в группе.\n\n"
        "Для повышения шансов на продажу, обязательно:\n"
        "📸 Добавляйте качественные фото\n"
        "💬 Делайте подробное описание товара\n\n"
        "Выберите действие:"
    )
    await message.answer(welcome_text, reply_markup=main_menu_keyboard, parse_mode="HTML")


@dp.callback_query(F.data == "info_adv") 
async def handle_order_ad(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    try: await callback.message.delete()
    except: pass

    adv_text = (
        "📣 Разместить рекламу\n\n"
        "Продвигайте свои товары и услуги в Базар Варшава 🛍️!\n"
        "📩 По вопросам размещения пишите: @foxtyro"
    )
    await callback.message.answer(adv_text, reply_markup=adv_contact_keyboard, parse_mode="HTML")


@dp.callback_query(F.data == "info_support") 
async def handle_support(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    try: await callback.message.delete()
    except: pass

    support_text = "🛠️ Служба поддержки\n\n📩 Напишите администратору: @foxtyro"
    await callback.message.answer(support_text, reply_markup=adv_contact_keyboard, parse_mode="HTML")


# --- УДАЛЕНИЕ ПОСТА ---
@dp.callback_query(F.data == "info_delete") 
async def handle_delete_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    await state.clear()
    try: await callback.message.delete()
    except: pass
        
    posts = AD_PUBLISHED_STORAGE.get(user_id, [])
    if not posts:
        await callback.message.answer("❌ У вас нет активных объявлений.", reply_markup=main_menu_return_keyboard)
        return

    post_keyboard = get_user_posts_keyboard(user_id, AD_PUBLISHED_STORAGE)
    await callback.message.answer("🗑️ Выберите объявление для удаления:", reply_markup=post_keyboard)
    await state.set_state(AdSteps.awaiting_post_to_delete)

@dp.callback_query(AdSteps.awaiting_post_to_delete, F.data.startswith("del_post_"))
async def handle_post_selection(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try: await callback.message.delete()
    except: pass
    
    user_id = callback.from_user.id
    try: post_index = int(callback.data.split("_")[2])
    except: return await callback.message.answer("❌ Ошибка.")
        
    posts = AD_PUBLISHED_STORAGE.get(user_id, [])
    if post_index >= len(posts): return await callback.message.answer("❌ Объявление не найдено.")
        
    post_to_delete = posts[post_index]
    await state.update_data(post_index_to_delete=post_index)
    
    await callback.message.answer(
        f"Вы уверены, что хотите удалить это объявление?\nДействие необратимо.",
        reply_markup=get_delete_confirmation_keyboard(post_index)
    )
    await state.set_state(AdSteps.awaiting_delete_confirmation)

@dp.callback_query(AdSteps.awaiting_delete_confirmation, F.data.startswith("confirm_del_"))
async def handle_delete_confirmation(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Удаляем...")
    try: await callback.message.delete()
    except: pass
    
    user_id = callback.from_user.id
    data = await state.get_data()
    post_index = data.get('post_index_to_delete')
    posts = AD_PUBLISHED_STORAGE.get(user_id, [])
    
    if post_index is None or post_index >= len(posts):
        await state.clear()
        return await callback.message.answer("❌ Ошибка.", reply_markup=main_menu_return_keyboard)
    
    post_to_delete = posts[post_index]
    message_ids_to_delete = post_to_delete['msg_id']
    if not isinstance(message_ids_to_delete, list): message_ids_to_delete = [message_ids_to_delete]
    
    deleted_count = 0
    for msg_id in message_ids_to_delete:
        try:
            await bot.delete_message(chat_id=TARGET_CHANNEL_ID, message_id=msg_id)
            deleted_count += 1
        except Exception as e:
            if "not found" in str(e).lower(): deleted_count += 1
            else: logging.warning(f"Failed to delete {msg_id}: {e}")

    if deleted_count > 0:
        AD_PUBLISHED_STORAGE[user_id].pop(post_index)
        if not AD_PUBLISHED_STORAGE.get(user_id): del AD_PUBLISHED_STORAGE[user_id]
        save_data() 
        await callback.message.answer("✅ Объявление удалено!", reply_markup=main_menu_return_keyboard)
    else:
        await callback.message.answer("⚠️ Ошибка удаления.", reply_markup=adv_contact_keyboard)
    await state.clear()

@dp.callback_query(AdSteps.awaiting_delete_confirmation, F.data.startswith("cancel_del_"))
async def handle_delete_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Отменено.")
    try: await callback.message.delete()
    except: pass
    await state.clear()
    await callback.message.answer("❌ Отменено.", reply_markup=main_menu_return_keyboard)


# --- ФЛОУ СОЗДАНИЯ ОБЪЯВЛЕНИЯ ---

@dp.callback_query(F.data.in_({"sale_start", "buy_start", "give_away_start"}))
async def start_ad_flow(callback: CallbackQuery, state: FSMContext):
    await callback.answer() 
    ad_type = 'sell'
    if callback.data == "buy_start": ad_type = 'buy'
    elif callback.data == "give_away_start": ad_type = 'give'

    try: await callback.message.delete()
    except: pass
    
    await state.update_data(ad_type=ad_type, photos=[], last_photo_update=0) 
    if ad_type == 'sell': await show_category_menu(callback.message, state) 
    else:
        await state.update_data(category="general")
        await start_photo_step(callback.message, state)

async def show_category_menu(message: types.Message, state: FSMContext):
    await message.answer("Выберите категорию:", reply_markup=category_keyboard)
    await state.set_state(AdSteps.choosing_category)

@dp.callback_query(AdSteps.choosing_category, F.data.startswith("cat_"))
async def category_chosen(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    category_code = callback.data.split("_")[1] 
    await state.update_data(category=category_code)
    try: await callback.message.delete()
    except: pass
    await start_photo_step(callback.message, state)

async def start_photo_step(message: types.Message, state: FSMContext):
    await message.answer("Шаг 1: Фото\nПришлите фото (до 10 шт.) или пропустите.", reply_markup=photo_step_keyboard)
    await state.set_state(AdSteps.awaiting_photo_or_skip)

@dp.callback_query(AdSteps.awaiting_photo_or_skip, F.data == "photo_skip")
async def handle_photo_skip(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Пропускаем фото.")
    await state.update_data(photos=[])
    try: await callback.message.delete()
    except: pass
    await start_description_step(callback.message.chat.id, state)

@dp.callback_query(AdSteps.awaiting_photo_or_skip, F.data == "photo_continue")
async def handle_photo_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try: await callback.message.delete()
    except: pass
    msg = await bot.send_message(callback.from_user.id, "📸 Шаг 1: Загрузите фото")
    await state.update_data(photo_status_message_id=msg.message_id) 
    await state.set_state(AdSteps.awaiting_photo_or_skip)

@dp.message(F.photo, AdSteps.awaiting_photo_or_skip) 
async def handle_photo_input(message: Message, state: FSMContext):
    try: await message.delete()
    except: pass
    data = await state.get_data()
    current_photos = data.get('photos', [])
    
    if len(current_photos) < MAX_PHOTOS:
        if message.photo[-1].file_id not in current_photos:
            current_photos.append(message.photo[-1].file_id)
            await state.update_data(photos=current_photos)
    
    current_time = time.time()
    await state.update_data(last_photo_update=current_time)
    status_msg = await message.answer(f"✅ Фото принято ({len(current_photos)}/{MAX_PHOTOS})")
    await asyncio.sleep(2.0) 
    try: await status_msg.delete()
    except: pass

    updated_data = await state.get_data()
    if updated_data.get('last_photo_update', 0) != current_time: return

    if data.get('photo_status_message_id'):
        try: await bot.delete_message(chat_id=message.chat.id, message_id=data['photo_status_message_id'])
        except: pass
    await start_description_step(message.chat.id, state)

async def start_description_step(chat_id: int, state: FSMContext):
    data = await state.get_data()
    msg = await bot.send_message(chat_id, f"Шаг 2: Описание\nФото принято: {len(data.get('photos', []))}\nВведите описание товара и цену.")
    await state.update_data(description_message_id=msg.message_id) 
    await state.set_state(AdSteps.entering_desc)

@dp.message(F.text, AdSteps.entering_desc)
async def handle_description_input(message: Message, state: FSMContext):
    description = message.text.strip()
    data = await state.get_data()
    
    if data.get('description_error_id'):
        try: await bot.delete_message(message.chat.id, data['description_error_id'])
        except: pass

    if len(description) < 20: 
        try: await message.delete()
        except: pass
        err = await message.answer("⚠️ Описание слишком короткое (минимум 20 символов).")
        await state.update_data(description_error_id=err.message_id)
        return
        
    if data.get('description_message_id'):
        try: await bot.delete_message(message.chat.id, data['description_message_id'])
        except: pass
    try: await message.delete()
    except: pass
        
    await state.update_data(description=description) 
    await start_contact_step(message, state) 

async def start_contact_step(message: types.Message, state: FSMContext):
    msg = await message.answer("Шаг 3: Контакты\nУкажите телефон или пропустите.", reply_markup=skip_contact_keyboard)
    await state.update_data(contact_message_id=msg.message_id)
    await state.set_state(AdSteps.entering_contact)

@dp.message(F.text, AdSteps.entering_contact)
async def handle_contact_input(message: Message, state: FSMContext):
    try: await message.delete()
    except: pass
    if (await state.get_data()).get('contact_message_id'):
        try: await bot.delete_message(message.chat.id, (await state.get_data())['contact_message_id'])
        except: pass
    await state.update_data(contact=message.text.strip())
    await show_final_preview(message, state)

@dp.callback_query(AdSteps.entering_contact, F.data == "contact_skip")
async def handle_contact_skip(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try: await callback.message.delete()
    except: pass
    await state.update_data(contact=None)
    await show_final_preview(callback.message, state)

@dp.callback_query(AdSteps.awaiting_final_action, F.data == "final_cancel")
async def handle_final_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Отменено.")
    await clear_preview_messages(callback.message.chat.id, state)
    await cmd_start_or_callback(callback, state) 

@dp.callback_query(AdSteps.awaiting_final_action, F.data == "final_edit_text")
async def handle_final_edit_text(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await clear_preview_messages(callback.message.chat.id, state)
    await start_description_step(callback.from_user.id, state)


# 🔥🔥🔥 ОСНОВНАЯ ФУНКЦИЯ ПУБЛИКАЦИИ С АВТО-АПРУВОМ 🔥🔥🔥

@dp.callback_query(AdSteps.awaiting_final_action, F.data == "final_publish")
async def handle_final_publish(callback: CallbackQuery, state: FSMContext):
    """Отправляет объявление на проверку AI + Авто-публикация."""
    await callback.answer()
    await clear_preview_messages(callback.message.chat.id, state)
    
    ad_data = await state.get_data()
    ad_data['user_id'] = callback.from_user.id 

    # 1. НЕЙТРАЛЬНОЕ СООБЩЕНИЕ (не выдаем ИИ)
    processing_msg = await callback.message.answer("⏳ Проверяем ваше объявление на соответствие правилам...")

    # 2. ПРОВЕРКА AI
    ai_result = await moderate_ad_with_ai(bot, ad_data)
    
    try: await processing_msg.delete()
    except: pass

    decision = ai_result.get("decision", "manual")
    reason = ai_result.get("reason", "Требуется проверка модератора")

    # --- СЦЕНАРИЙ А: ОТКЛОНЕНО ---
    if decision == "reject":
        await callback.message.answer(
            f"❌ <b>Ваше объявление отклонено системой модерации.</b>\n\n"
            f"⚠️ <b>Причина:</b> {reason}\n\n"
            f"Пожалуйста, исправьте и попробуйте снова.",
            parse_mode="HTML",
            reply_markup=main_menu_return_keyboard
        )
        await state.clear()
        return

    # --- СЦЕНАРИЙ Б: АВТО-ПУБЛИКАЦИЯ (УСПЕХ) ---
    if decision == "approve":
        success, result = await publish_post_to_channel(bot, ad_data)
        
        if success:
            # Генерация ссылки
            sent_message_ids = result
            clean_channel_id = str(TARGET_CHANNEL_ID)[4:] if str(TARGET_CHANNEL_ID).startswith("-100") else str(TARGET_CHANNEL_ID)
            post_link = f"https://t.me/c/{clean_channel_id}/{sent_message_ids[0]}"
            
            view_ad_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👀 Посмотреть", url=post_link)],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="start")]
            ])
            await callback.message.answer("🎉 Объявление успешно опубликовано!", reply_markup=view_ad_kb)
        else:
            await callback.message.answer(f"⚠️ Ошибка публикации: {result}")
        
        await state.clear()
        return

    # --- СЦЕНАРИЙ В: РУЧНАЯ ПРОВЕРКА (ЕСЛИ ИИ НЕ УВЕРЕН) ---
    # Если decision == "manual", отправляем админам
    
    ad_id = str(int(time.time())) 
    AD_PENDING_STORAGE[ad_id] = ad_data 

    ad_type = ad_data.get('ad_type')
    cat = ad_data.get('category', '')
    title_type = "ТОВАР"
    if ad_type == 'buy': title_type = "КУПЛЮ"
    elif ad_type == 'give': title_type = "ОТДАМ ДАРОМ"
    elif cat: title_type = cat.upper()

    caption = get_ad_text(ad_data)
    ai_verdict_admin = f"\n\n🤖 <b>AI:</b> ⚠️ MANUAL CHECK\n💭 {reason}"

    moderation_caption = (
        f"🛡 МОДЕРАЦИЯ (ID: {ad_id}) — {title_type}\n"
        f"{ai_verdict_admin}\n\n"
        f"{caption}\n\n"
        f"👤 @{callback.from_user.username or callback.from_user.id}"
    )

    photo_ids = ad_data.get('photos', [])
    sent_message_ids = []

    try:
        if photo_ids:
            media_group = []
            for i, photo_id in enumerate(photo_ids):
                watermarked_photo_data = await apply_watermark(bot, photo_id)
                watermarked_photo_data.seek(0) 
                photo_file = BufferedInputFile(watermarked_photo_data.read(), filename=f"mod_wm_{i}.jpg")
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo_file, caption=moderation_caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=photo_file))
            msgs = await bot.send_media_group(chat_id=MODERATION_CHAT_ID, media=media_group)
            for msg in msgs: sent_message_ids.append(msg.message_id)
        else:
            sent_msg = await bot.send_message(chat_id=MODERATION_CHAT_ID, text=moderation_caption, parse_mode="HTML")
            sent_message_ids.append(sent_msg.message_id)

        await bot.send_message(MODERATION_CHAT_ID, f"Действие для ID: {ad_id}", reply_markup=get_moderation_keyboard(ad_id))
        
        # Пользователю пишем нейтрально
        await callback.message.answer("📨 Объявление отправлено на проверку модератору.", reply_markup=main_menu_return_keyboard)
        await state.clear()
        AD_PENDING_STORAGE[ad_id]['moderator_message_ids'] = sent_message_ids 

    except Exception as e:
        logging.error(f"Err mod: {e}")
        await callback.message.answer("❌ Ошибка.")


@dp.callback_query(F.data.startswith("approve_"))
async def admin_approve_ad(callback: CallbackQuery):
    """РУЧНОЕ одобрение админом (для тех случаев, когда ИИ отправил на manual)."""
    await callback.answer("Одобрено!")
    ad_id = callback.data.split("_")[1]
    ad_data = AD_PENDING_STORAGE.get(ad_id)

    if not ad_data:
        return await callback.message.edit_text(f"❌ Не найдено {ad_id}")

    # Используем ту же функцию публикации
    success, result = await publish_post_to_channel(bot, ad_data)
    
    new_text = callback.message.text + "\n\n"
    if success:
        new_text += "✅ ОПУБЛИКОВАНО"
        # Уведомление юзера
        try:
            clean_channel_id = str(TARGET_CHANNEL_ID)[4:] if str(TARGET_CHANNEL_ID).startswith("-100") else str(TARGET_CHANNEL_ID)
            post_link = f"https://t.me/c/{clean_channel_id}/{result[0]}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👀 Посмотреть", url=post_link)]])
            await bot.send_message(ad_data['user_id'], "🎉 Ваше объявление одобрено и опубликовано!", reply_markup=kb)
        except: pass
        del AD_PENDING_STORAGE[ad_id]
    else:
        new_text += f"⚠️ ОШИБКА: {result}"

    await callback.message.edit_text(new_text)


@dp.callback_query(F.data.startswith("reject_"))
async def admin_reject_ad(callback: CallbackQuery):
    await callback.answer("Отклонено!")
    ad_id = callback.data.split("_")[1]
    ad_data = AD_PENDING_STORAGE.get(ad_id)
    if ad_data:
        try: await bot.send_message(ad_data['user_id'], f"❌ Ваше объявление (ID: {ad_id}) отклонено модератором.", reply_markup=main_menu_return_keyboard)
        except: pass
        del AD_PENDING_STORAGE[ad_id]
    await callback.message.edit_text(callback.message.text + "\n\n❌ ОТКЛОНЕНО")


async def main():
    logging.info("BOT STARTED...")
    load_data() 
    await bot.delete_webhook(drop_pending_updates=True)
    try: await dp.start_polling(bot)
    finally:
        save_data()
        await bot.session.close() 

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: logging.info("Stop.") 
    except Exception as e: logging.error(f"Fatal: {e}")