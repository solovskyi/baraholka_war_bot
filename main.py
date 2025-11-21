# main.py

import asyncio
import logging
import time
from typing import Union

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
                # Функция apply_watermark должна быть импортирована из utils
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
        
    # ЕСЛИ ФОТО НЕ БЫЛО ИЛИ ВЫШЛА ОШИБКА ПРИ ОТПРАВКЕ ФОТО
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


# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
@dp.callback_query(F.data == "start")
async def cmd_start_or_callback(callback_or_message: types.CallbackQuery | types.Message, state: FSMContext):
    """Обрабатывает команду /start или колбэк 'start' и выводит главное меню."""
    
    if isinstance(callback_or_message, types.CallbackQuery):
        message = callback_or_message.message
        await callback_or_message.answer()
        try:
            await callback_or_message.message.delete()
        except Exception:
            pass
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


# --- ХЕНДЛЕР: ЗАКАЗ РЕКЛАМЫ ---

@dp.callback_query(F.data == "info_adv") 
async def handle_order_ad(callback: CallbackQuery, state: FSMContext):
    """Показывает информацию о размещении рекламы."""
    await callback.answer()
    
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass

    adv_text = (
        "📣 Разместить рекламу\n\n"
        "Продвигайте свои товары и услуги в Базар Варшава 🛍️ — быстро, удобно и эффективно!\n\n"
        "📌 Закрепление вашей публикации в любом разделе\n"
        "🗓 На 1 неделю — 50 zł\n"
        "📆 На 1 месяц — 150 zł\n\n"
        "🌐 Продвижение внешних ресурсов\n"
        "(Telegram-каналы, Instagram и другие платформы)\n"
        "🗓 Неделя в закрепе — 150 zł\n"
        "📆 Месяц в закрепе — 300 zł\n\n"
        "🛠️ Размещение в разделе «Услуги»\n"
        "📝 1 публикация — 25 zł\n"
        "➤ Пост остаётся навсегда.\n\n"
        "📩 По вопросам размещения рекламы пишите:\n"
        "@foxtyro\n\n"
        "✨ Пусть о вас узнают те, кому это важно!"
    )
    
    await callback.message.answer(
        adv_text,
        reply_markup=adv_contact_keyboard,
        parse_mode="HTML"
    )

# --- КОНЕЦ ХЕНДЛЕРА РЕКЛАМЫ ---


# --- ХЕНДЛЕР: ПОДДЕРЖКА ---

@dp.callback_query(F.data == "info_support") 
async def handle_support(callback: CallbackQuery, state: FSMContext):
    """Показывает контактную информацию службы поддержки."""
    await callback.answer()
    
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass

    support_text = (
        "🛠️ Служба поддержки\n\n"
        "Если у вас возникли вопросы, связанные с работой бота, модерацией, оплатой или техническими проблемами:\n\n"
        "📩 Напишите нашему администратору:\n"
        "@foxtyro\n\n"
        "Мы постараемся ответить максимально быстро!"
    )
    
    await callback.message.answer(
        support_text,
        reply_markup=adv_contact_keyboard, 
        parse_mode="HTML"
    )

# --- КОНЕЦ ХЕНДЛЕРА ПОДДЕРЖКИ ---


# --- ХЕНДЛЕР: НАЧАЛО УДАЛЕНИЯ ПОСТА ---

@dp.callback_query(F.data == "info_delete") 
async def handle_delete_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс удаления объявления."""
    await callback.answer()
    user_id = callback.from_user.id
    
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    posts = AD_PUBLISHED_STORAGE.get(user_id, [])
    
    if not posts:
        await callback.message.answer(
            "❌ У вас нет активных опубликованных объявлений, которые можно удалить.",
            reply_markup=main_menu_return_keyboard
        )
        return

    # Динамически генерируем клавиатуру со списком постов
    post_keyboard = get_user_posts_keyboard(user_id, AD_PUBLISHED_STORAGE)
    
    await callback.message.answer(
        "🗑️ Выберите объявление, которое хотите удалить:",
        reply_markup=post_keyboard
    )
    
    await state.set_state(AdSteps.awaiting_post_to_delete)

# --- ХЕНДЛЕР: ВЫБОР ПОСТА ДЛЯ УДАЛЕНИЯ ---
@dp.callback_query(AdSteps.awaiting_post_to_delete, F.data.startswith("del_post_"))
async def handle_post_selection(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор поста из списка для удаления."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    user_id = callback.from_user.id
    try:
        post_index = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        return await callback.message.answer("❌ Ошибка идентификации объявления.")
        
    posts = AD_PUBLISHED_STORAGE.get(user_id, [])
    
    if post_index >= len(posts):
        return await callback.message.answer("❌ Объявление не найдено.")
        
    post_to_delete = posts[post_index]
    
    # Сохраняем индекс поста в FSM для шага подтверждения
    await state.update_data(post_index_to_delete=post_index)
    
    # Создаем текст для подтверждения (показываем первую строку описания)
    full_description = post_to_delete['description']
    
    # Находим первую непустую строку, игнорируя служебные
    preview_text = "Нет описания"
    PREFIXES_TO_IGNORE = ('🛒 #КУПЛЮ', '🎁 #ОТДАМ_ДАРОМ', '👤 @', '📞 ', 'Базар Варшава')
    
    for line in full_description.split('\n'):
        line = line.strip()
        if line and not line.startswith(PREFIXES_TO_IGNORE):
            preview_text = line
            break
            
    # msg_id - это список, берем первый элемент для отображения ID
    display_msg_id = post_to_delete['msg_id'][0] if isinstance(post_to_delete['msg_id'], list) else post_to_delete['msg_id']
    
    await callback.message.answer(
        f"Вы уверены, что хотите удалить это объявление?\n\n"
        f"**Описание:** `{preview_text}`\n"
        f"**ID сообщения:** `{display_msg_id}`\n\n"
        f"Действие необратимо.",
        reply_markup=get_delete_confirmation_keyboard(post_index),
        parse_mode="Markdown" 
    )
    
    await state.set_state(AdSteps.awaiting_delete_confirmation)

# --- ХЕНДЛЕР: ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ ---
@dp.callback_query(AdSteps.awaiting_delete_confirmation, F.data.startswith("confirm_del_"))
async def handle_delete_confirmation(callback: CallbackQuery, state: FSMContext):
    """Удаляет объявление из канала и из хранилища."""
    await callback.answer("Удаляем...")
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    user_id = callback.from_user.id
    
    data = await state.get_data()
    post_index = data.get('post_index_to_delete')
    
    posts = AD_PUBLISHED_STORAGE.get(user_id, [])
    
    if post_index is None or post_index >= len(posts):
        await state.clear()
        return await callback.message.answer("❌ Ошибка: Объявление не найдено. Начните снова.", reply_markup=main_menu_return_keyboard)
    
    post_to_delete = posts[post_index]
    
    # message_ids_to_delete теперь список ID сообщений (для альбома)
    message_ids_to_delete = post_to_delete['msg_id']
    if not isinstance(message_ids_to_delete, list):
         message_ids_to_delete = [message_ids_to_delete] # Если это одиночный пост, делаем список
    
    deletion_successful = False
    deleted_count = 0
    
    # Перебираем и удаляем каждое сообщение из альбома
    for msg_id in message_ids_to_delete:
        try:
            await bot.delete_message(
                chat_id=TARGET_CHANNEL_ID, 
                message_id=msg_id,
            )
            deleted_count += 1
        except Exception as e:
            # Если сообщение уже удалено или не найдено, считаем это успешным результатом для UX
            if "message to delete not found" in str(e).lower():
                 deleted_count += 1
            else:
                 logging.warning(f"Failed to delete message ID {msg_id}: {e}")

    # Считаем удаление успешным, если мы попытались удалить все сообщения, и их больше нуля
    if deleted_count == len(message_ids_to_delete) and deleted_count > 0:
        deletion_successful = True
    
    if deletion_successful:
        # Удаляем пост из хранилища
        AD_PUBLISHED_STORAGE[user_id].pop(post_index)
        
        # Очищаем хранилище, если список постов стал пустым
        if not AD_PUBLISHED_STORAGE.get(user_id):
            del AD_PUBLISHED_STORAGE[user_id]
            
        # НОВОЕ: Сохраняем данные после успешного удаления
        save_data() 

        await callback.message.answer("✅ Объявление успешно удалено!", reply_markup=main_menu_return_keyboard)
    else:
        await callback.message.answer(
            "⚠️ Ошибка удаления. Обратитесь в поддержку (@foxtyro).", 
            reply_markup=adv_contact_keyboard 
        )
        
    await state.clear()


# --- ХЕНДЛЕР: ОТМЕНА УДАЛЕНИЯ ---
@dp.callback_query(AdSteps.awaiting_delete_confirmation, F.data.startswith("cancel_del_"))
async def handle_delete_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменяет операцию удаления."""
    await callback.answer("Отменено.")
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    await state.clear()
    
    await callback.message.answer("❌ Удаление объявления отменено.", reply_markup=main_menu_return_keyboard)

# --- КОНЕЦ ХЕНДЛЕРОВ УДАЛЕНИЯ ---


@dp.callback_query(F.data.in_({"sale_start", "buy_start", "give_away_start"}))
async def start_ad_flow(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс создания объявления (Продажа, Покупка, Отдам даром)."""
    await callback.answer() 
    
    ad_type = 'sell'
    if callback.data == "buy_start":
        ad_type = 'buy'
    elif callback.data == "give_away_start":
        ad_type = 'give'

    try:
        await callback.message.delete()
    except: pass
    
    await state.update_data(
        ad_type=ad_type, 
        photos=[], 
        photo_status_message_id=None, 
        description_message_id=None, 
        contact_message_id=None,
        description_error_id=None,
        preview_message_ids=[], 
        last_photo_update=0 
    ) 
    
    if ad_type == 'sell':
        await show_category_menu(callback.message, state) 
    else:
        await state.update_data(category="general")
        await start_photo_step(callback.message, state)


async def show_category_menu(message: types.Message, state: FSMContext):
    """Показывает меню выбора категорий."""
    await message.answer(
        "Выберите категорию для вашего товара:",
        reply_markup=category_keyboard,
        parse_mode="HTML"
    )
    await state.set_state(AdSteps.choosing_category)


@dp.callback_query(AdSteps.choosing_category, F.data.startswith("cat_"))
async def category_chosen(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор категории и переходит к шагу с фото."""
    await callback.answer()
    category_code = callback.data.split("_")[1] 
    await state.update_data(category=category_code)
    try:
        await callback.message.delete()
    except: pass
    await start_photo_step(callback.message, state)


async def start_photo_step(message: types.Message, state: FSMContext):
    """Начинает первый шаг: загрузка фото."""
    await message.answer(
        "Шаг 1: Фото\n\nПришлите фото (до 10 шт.) или пропустите этот шаг.",
        reply_markup=photo_step_keyboard,
        parse_mode="HTML"
    )
    await state.set_state(AdSteps.awaiting_photo_or_skip)


@dp.callback_query(AdSteps.awaiting_photo_or_skip, F.data == "photo_skip")
async def handle_photo_skip(callback: CallbackQuery, state: FSMContext):
    """Пропускает шаг с фото."""
    await callback.answer("Пропускаем шаг с фото.")
    chat_id = callback.message.chat.id
    
    await state.update_data(photos=[], photo_status_message_id=None)
    await start_description_step(chat_id, state) 
    
    try:
        await callback.message.delete()
    except Exception:
        pass


@dp.callback_query(AdSteps.awaiting_photo_or_skip, F.data == "photo_continue")
async def handle_photo_start(callback: CallbackQuery, state: FSMContext):
    """Подтверждает начало загрузки фото."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    status_message = await bot.send_message(
        chat_id=callback.from_user.id,
        text="📸 Шаг 1: Загрузите фото (до 10шт.)"
    )
    await state.update_data(photo_status_message_id=status_message.message_id) 
    await state.set_state(AdSteps.awaiting_photo_or_skip)


@dp.message(F.photo, AdSteps.awaiting_photo_or_skip) 
async def handle_photo_input(message: Message, state: FSMContext):
    """Обрабатывает ввод фотографий (с Debounce для медиагрупп)."""
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    current_photos = data.get('photos', [])
    photo_status_message_id = data.get('photo_status_message_id')
    
    # ------------------ ЛОГИКА ОБРАБОТКИ ФОТО (DEBOUNCE) ------------------
    photo_file_id = message.photo[-1].file_id 
    max_photos_exceeded = False 
    
    if len(current_photos) < MAX_PHOTOS:
        if photo_file_id not in current_photos:
            current_photos.append(photo_file_id)
            await state.update_data(photos=current_photos)
    else:
        max_photos_exceeded = True 
    
    current_time = time.time()
    await state.update_data(last_photo_update=current_time)
    
    # Dynamic Status Message (feedback on photo acceptance/limit)
    status_text = "✅ Фото принято."
    if max_photos_exceeded:
        status_text = f"⚠️ Лимит фото ({MAX_PHOTOS} шт.) достигнут. Переходим к описанию."
        
    status_msg = await message.answer(status_text)
    
    await asyncio.sleep(2.0) # Debounce delay

    try:
        await status_msg.delete()
    except Exception:
        pass

    updated_data = await state.get_data()
    if updated_data.get('last_photo_update', 0) != current_time:
        return # Выход, если за время Debounce пришло новое фото

    logging.info(f"Transitioning to DESC. Photos saved: {len(updated_data.get('photos', []))}")

    if photo_status_message_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=photo_status_message_id)
        except Exception:
            pass
    
    await start_description_step(message.chat.id, state)
    # ------------------ КОНЕЦ ЛОГИКИ ОБРАБОТКИ ФОТО ------------------


async def start_description_step(chat_id: int, state: FSMContext):
    """Начинает второй шаг: ввод описания."""
    data = await state.get_data()
    photo_count = len(data.get('photos', [])) 
    ad_type = data.get('ad_type', 'sell')

    if ad_type == 'buy':
        intro = "Напишите, что именно вы ищете и ваш бюджет."
    elif ad_type == 'give':
        intro = "Опишите вещь, которую отдаете."
    else:
        intro = "Теперь напишите подробное описание товара (включая цену)."

    description_message = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"Шаг 2: Описание\n\n"
            f"Фотографий принято: {photo_count} шт.\n\n"
            f"{intro}"
        ),
        parse_mode="HTML"
    )
    await state.update_data(description_message_id=description_message.message_id) 
    await state.update_data(photo_status_message_id=None) 
    await state.set_state(AdSteps.entering_desc)


@dp.message(F.text, AdSteps.entering_desc)
async def handle_description_input(message: Message, state: FSMContext):
    """Обрабатывает ввод описания."""
    description = message.text.strip()
    data = await state.get_data()

    previous_error_id = data.get('description_error_id')
    if previous_error_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=previous_error_id)
        except Exception:
            pass
        await state.update_data(description_error_id=None)

    if len(description) < 20: 
        try:
            await message.delete()
        except Exception:
            pass
        error_message = await message.answer("Описание слишком короткое (минимум 20 символов).")
        await state.update_data(description_error_id=error_message.message_id)
        return
        
    description_message_id = data.get('description_message_id')
    if description_message_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=description_message_id)
        except Exception:
            pass
            
    try:
        await message.delete()
    except Exception:
        pass
        
    await state.update_data(description=description, description_message_id=None) 
    await start_contact_step(message, state) 


async def start_contact_step(message: types.Message, state: FSMContext):
    """Начинает третий шаг: ввод контактов."""
    contact_message = await message.answer(
        "Шаг 3: Контакты\n\n"
        "Укажите ваш контактный номер телефона.",
        reply_markup=skip_contact_keyboard,
        parse_mode="HTML"
    )
    await state.update_data(contact_message_id=contact_message.message_id)
    await state.set_state(AdSteps.entering_contact)


@dp.message(F.text, AdSteps.entering_contact)
async def handle_contact_input(message: Message, state: FSMContext):
    """Обрабатывает ввод контактов."""
    contact = message.text.strip()
    data = await state.get_data()
    
    if data.get('contact_message_id'):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=data['contact_message_id'])
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass
        
    await state.update_data(contact=contact, contact_message_id=None)
    await show_final_preview(message, state)


@dp.callback_query(AdSteps.entering_contact, F.data == "contact_skip")
async def handle_contact_skip(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает пропуск ввода контактов."""
    await callback.answer("Контакты пропущены.")
    data = await state.get_data()
    
    if data.get('contact_message_id'):
        try:
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=data['contact_message_id'])
        except Exception:
            pass
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    await state.update_data(contact=None, contact_message_id=None)
    await show_final_preview(callback.message, state)


@dp.callback_query(AdSteps.awaiting_final_action, F.data == "final_cancel")
async def handle_final_cancel(callback: CallbackQuery, state: FSMContext):
    """Отменяет операцию и возвращается в главное меню."""
    await callback.answer("Отменено.")
    await clear_preview_messages(callback.message.chat.id, state)
    await cmd_start_or_callback(callback, state) 


@dp.callback_query(AdSteps.awaiting_final_action, F.data == "final_edit_text")
async def handle_final_edit_text(callback: CallbackQuery, state: FSMContext):
    """Возвращается к шагу ввода описания для редактирования."""
    await callback.answer("Редактирование...")
    await clear_preview_messages(callback.message.chat.id, state)
    await start_description_step(callback.from_user.id, state)


@dp.callback_query(AdSteps.awaiting_final_action, F.data == "final_publish")
async def handle_final_publish(callback: CallbackQuery, state: FSMContext):
    """Отправляет объявление на модерацию."""
    await callback.answer("Отправка на модерацию...")
    await clear_preview_messages(callback.message.chat.id, state)
    
    ad_id = str(int(time.time())) 
    ad_data = await state.get_data()
    AD_PENDING_STORAGE[ad_id] = ad_data 
    AD_PENDING_STORAGE[ad_id]['user_id'] = callback.from_user.id 
    
    ad_type = ad_data.get('ad_type')
    cat = ad_data.get('category', '')
    title_type = "ТОВАР"
    if ad_type == 'buy': title_type = "КУПЛЮ"
    elif ad_type == 'give': title_type = "ОТДАМ ДАРОМ"
    elif cat: title_type = cat.upper()

    caption = get_ad_text(ad_data)

    moderation_caption = (
        f"⚠️ МОДЕРАЦИЯ (ID: {ad_id}) — {title_type}\n\n"
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
            for msg in msgs: # Сохраняем все ID
                sent_message_ids.append(msg.message_id)

        else:
            sent_msg = await bot.send_message(chat_id=MODERATION_CHAT_ID, text=moderation_caption, parse_mode="HTML")
            sent_message_ids.append(sent_msg.message_id)

        await bot.send_message(
            chat_id=MODERATION_CHAT_ID,
            text=f"Действие для объявления ID: {ad_id}",
            reply_markup=get_moderation_keyboard(ad_id)
        )
        
        msg = await callback.message.answer("🎉 Ваше объявление отправлено на модерацию!", reply_markup=main_menu_return_keyboard)
        await state.clear()
        await state.update_data(main_menu_message_id=msg.message_id)

    except Exception as e:
        logging.error(f"Ошибка отправки модератору: {e}")
        await callback.message.answer("❌ Ошибка при отправке заявки.")
        return 
    
    AD_PENDING_STORAGE[ad_id]['moderator_message_ids'] = sent_message_ids 


@dp.callback_query(F.data.startswith("approve_"))
async def admin_approve_ad(callback: CallbackQuery):
    """Обрабатывает одобрение объявления модератором и публикует его в канале."""
    await callback.answer("Одобрено!")
    ad_id = callback.data.split("_")[1]
    ad_data = AD_PENDING_STORAGE.get(ad_id)

    if not ad_data:
        return await callback.message.edit_text(f"❌ Объявление {ad_id} не найдено.")

    ad_type = ad_data.get('ad_type')
    category_code = ad_data.get('category')
    
    topic_id = None
    if ad_type == 'buy':
        topic_id = TOPIC_BUY
    elif ad_type == 'give':
        topic_id = TOPIC_GIVE
    else:
        topic_id = CATEGORY_TOPICS.get(category_code)

    final_caption = get_ad_text(ad_data)
    
    # --- ДОБАВЛЕНИЕ АВТОРА К ФИНАЛЬНОМУ ПОСТУ ---
    user_id = ad_data.get('user_id')
    try:
        user_info = await bot.get_chat(chat_id=user_id)
        author_identifier = user_info.username or user_info.id
        author_line = f"\n\n👤 @{author_identifier}"
        final_caption += author_line
    except Exception as e:
        logging.error(f"Failed to fetch user info for ID {user_id}: {e}")
        pass
    # --- КОНЕЦ ДОБАВЛЕНИЯ АВТОРА ---
    
    photo_ids = ad_data.get('photos', [])
    posting_successful = False
    error_message = ""
    
    sent_message_id = None
    sent_message_ids = [] # Список для всех ID сообщений в канале

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
            for msg in msgs: # Сохраняем все ID
                sent_message_ids.append(msg.message_id)
            
            sent_message_id = sent_message_ids[0] # Сохраняем первый ID для ссылки

        else:
            sent_msg = await bot.send_message(chat_id=TARGET_CHANNEL_ID, text=final_caption, parse_mode="HTML", message_thread_id=topic_id)
            sent_message_id = sent_msg.message_id
            sent_message_ids.append(sent_message_id) 
        
        posting_successful = True

    except Exception as e:
        logging.error(f"ERROR: {e}")
        error_message = str(e)
    
    new_mod_text = callback.message.text + "\n\n"
    if posting_successful:
        topic_info = f"(Ветка {topic_id})" if topic_id else ""
        new_mod_text += f"✅ ОПУБЛИКОВАНО {topic_info}"
        
        # --- СОХРАНЕНИЕ В БАЗУ ОПУБЛИКОВАННЫХ ПОСТОВ ---
        post_data = {
            'msg_id': sent_message_ids, # Сохраняем СПИСОК всех ID
            'description': final_caption,
            'topic_id': topic_id,
        }
        user_id_int = ad_data['user_id']
        if user_id_int not in AD_PUBLISHED_STORAGE:
            AD_PUBLISHED_STORAGE[user_id_int] = []
        AD_PUBLISHED_STORAGE[user_id_int].append(post_data)
        
        # НОВОЕ: Сохраняем данные после успешной публикации
        save_data() 
        # -------------------------------------------------------------
        
    else:
        new_mod_text += f"⚠️ ОШИБКА: {error_message}"

    await callback.message.edit_text(new_mod_text)
    
    if posting_successful:
        try:
            # --- ГЕНЕРАЦИЯ ССЫЛКИ НА ПОСТ ---
            clean_channel_id = str(TARGET_CHANNEL_ID)[4:] if str(TARGET_CHANNEL_ID).startswith("-100") else str(TARGET_CHANNEL_ID)
            link_id = sent_message_ids[0] if sent_message_ids else sent_message_id
            post_link = f"https://t.me/c/{clean_channel_id}/{link_id}"
            
            # Клавиатура с кнопкой "Посмотреть"
            view_ad_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👀 Посмотреть объявление", url=post_link)],
                [InlineKeyboardButton(text="🏠 На главную", callback_data="start")]
            ])

            await bot.send_message(
                ad_data['user_id'], 
                f"🎉 Ваше объявление (ID: {ad_id}) одобрено и опубликовано!", 
                reply_markup=view_ad_kb
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление юзеру: {e}") 
        
        del AD_PENDING_STORAGE[ad_id]


@dp.callback_query(F.data.startswith("reject_"))
async def admin_reject_ad(callback: CallbackQuery):
    """Обрабатывает отклонение объявления модератором."""
    await callback.answer("Отклонено!")
    ad_id = callback.data.split("_")[1]
    ad_data = AD_PENDING_STORAGE.get(ad_id)

    if ad_data:
        try:
            await bot.send_message(
                ad_data['user_id'], 
                f"❌ Ваше объявление (ID: {ad_id}) отклонено. Исправьте и отправьте снова.", 
                reply_markup=main_menu_return_keyboard
            )
        except: pass
        del AD_PENDING_STORAGE[ad_id]

    await callback.message.edit_text(callback.message.text + "\n\n❌ ОТКЛОНЕНО")


async def main():
    """Основная функция запуска бота с обработкой персистентности."""
    logging.info("BOT STARTED...")
    
    # 1. ЗАГРУЗКА ДАННЫХ ПЕРЕД ЗАПУСКОМ
    load_data() 
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    finally:
        # 2. СОХРАНЕНИЕ ДАННЫХ ПЕРЕД ОСТАНОВКОЙ
        save_data()
        await bot.session.close() 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Остановка бота инициирована пользователем.") 
    except Exception as e:
        logging.error(f"Фатальная ошибка во время выполнения бота: {e}")