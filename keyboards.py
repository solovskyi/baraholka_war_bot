# keyboards.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import AD_PUBLISHED_STORAGE # Требуется импорт для динамических функций

# --- 1. Основное Меню (Главное Меню) ---

main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="💰 Продать", callback_data="sale_start"), 
        InlineKeyboardButton(text="🛒 Купить", callback_data="buy_start")
    ],
    [
        InlineKeyboardButton(text="🎁 Отдам даром", callback_data="give_away_start"), 
        InlineKeyboardButton(text="🛠️ Поддержка", callback_data="info_support")
    ],
    [
        InlineKeyboardButton(text="📣 Заказать рекламу", callback_data="info_adv")
    ],
    [
        InlineKeyboardButton(text="🗑️ Удалить пост", callback_data="info_delete") # Callback для старта удаления
    ]
])

# --- 2. Клавиатура Категорий ---
category_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🚗 Автомобили • Запчасти", callback_data="cat_auto")],
    [InlineKeyboardButton(text="🚲 Велосипеды • Самокаты", callback_data="cat_bicycle")], 
    [InlineKeyboardButton(text="📱 Смартфоны • Планшеты", callback_data="cat_phones")], 
    [InlineKeyboardButton(text="💻 Компьютеры • Комплектующие", callback_data="cat_computers")],
    [InlineKeyboardButton(text="🎮 Консоли", callback_data="cat_consoles")],
    [InlineKeyboardButton(text="📺 Вся электроника", callback_data="cat_electronics")],
    [InlineKeyboardButton(text="🏠 Дом • Огород", callback_data="cat_home")],
    [InlineKeyboardButton(text="🐈 Животные • Товары", callback_data="cat_animals")],
    [InlineKeyboardButton(text="⚽ Спорт • Хобби", callback_data="cat_sport")],
    [InlineKeyboardButton(text="🤵 Мужская одежда", callback_data="cat_men_clothes")],
    [InlineKeyboardButton(text="👠 Женская одежда", callback_data="cat_women_clothes")],
    [InlineKeyboardButton(text="👶 Товары для детей", callback_data="cat_kids")],
    [InlineKeyboardButton(text="📌 Другое", callback_data="cat_other")],
    [InlineKeyboardButton(text="🔙 Назад", callback_data="start")]
])

# --- 3. Клавиатура для Фото-шага (Начало) ---
photo_step_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📸 Начать загрузку фото", callback_data="photo_continue")],
    [InlineKeyboardButton(text="➡️ Пропустить этот шаг", callback_data="photo_skip")]
])

# --- 4. Клавиатура для пропуска контактов ---
skip_contact_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="➡️ Пропустить", callback_data="contact_skip")]
])

# --- 5. Клавиатура финального превью ---
final_preview_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Опубликовать", callback_data="final_publish")],
    [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data="final_edit_text")],
    [InlineKeyboardButton(text="❌ Отмена и Главное меню", callback_data="final_cancel")]
])

# --- 6. Вспомогательные клавиатуры ---
main_menu_return_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🏠 На главную", callback_data="start")]
])

# --- 7. Клавиатура модератора ---
def get_moderation_keyboard(ad_id):
    """Генерирует клавиатуру с кнопками Одобрить/Отклонить для модератора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{ad_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{ad_id}")]
    ])

# --- 8. Клавиатура для рекламы/поддержки ---
adv_contact_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(
            text="📩 Написать администратору", 
            url="tg://resolve?domain=foxtyro" 
        )
    ],
    [
        InlineKeyboardButton(
            text="🏠 На главную", 
            callback_data="start"
        )
    ]
])

# --- 9. Функции для управления постами (УДАЛЕНИЕ) ---

def get_user_posts_keyboard(user_id: int, published_storage: dict) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру со списком постов пользователя для удаления."""
    posts = published_storage.get(user_id, [])
    
    buttons = []
    
    # Ключевые префиксы, которые нужно игнорировать в описании
    PREFIXES_TO_IGNORE = ('🛒 #КУПЛЮ', '🎁 #ОТДАМ_ДАРОМ', '👤 @', '📞 ', 'Базар Варшава')

    for i, post in enumerate(posts):
        full_desc = post.get('description', f"Объявление #{post.get('msg_id', i+1)}")
        
        display_text = "Нет описания"
        
        # Находим первый неслужебный, непустой строковый элемент
        for line in full_desc.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Проверяем, начинается ли строка с игнорируемых префиксов
            is_service_line = False
            for prefix in PREFIXES_TO_IGNORE:
                if line.startswith(prefix):
                    is_service_line = True
                    break
            
            if not is_service_line:
                display_text = line
                break
        
        # Обрезание текста для кнопки
        if len(display_text) > 40:
            display_text = display_text[:37] + "..."

        # callback: del_post_<index>
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑️ {display_text}",
                callback_data=f"del_post_{i}"
            )
        ])
        
    buttons.append([
        InlineKeyboardButton(text="🏠 На главную", callback_data="start")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_confirmation_keyboard(post_index: int) -> InlineKeyboardMarkup:
    """Клавиатура для финального подтверждения удаления."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Удалить навсегда", callback_data=f"confirm_del_{post_index}"),
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_del_{post_index}"),
        ]
    ])