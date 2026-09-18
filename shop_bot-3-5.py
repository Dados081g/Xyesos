import asyncio
import sqlite3

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    MessageEntity,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# ======================= НАСТРОЙКИ =======================

BOT_TOKEN = "8342142309:AAHnGHfqM5M0_PI1WjJkfscvRk-yZemM8Ic"          # токен от @BotFather
ADMIN_ID = 123456789                   # ваш Telegram ID (узнать можно у @userinfobot)
ADMIN_PASSWORD = "maksumtop1"          # пароль для входа в /admin
CARD_NUMBER = "2202 2083 0536 9622"
CHANNEL_LINK = "https://t.me/+0D3hMBZtdcc3Y2Uy"

PRIVACY_LINK = "https://telegra.ph/Politika-konfidencialnosti-09-18-102"
AGREEMENT_LINK = "https://telegra.ph/Polzovatelskoe-soglashenie-09-18-64"

SUPPORT_USERNAME = "@Forevebz"                   # кнопка "Помощь"
# Ссылка, которую получает покупатель сразу после оплаты любого товара.
# ЗАМЕНИТЕ на настоящую ссылку на приватный канал/архив с файлами.
PRIVATE_FILES_LINK = "https://t.me/+ССЫЛКА_НА_ПРИВАТКУ"

# ID премиум-эмодзи
EMOJI_GIFT = "5983580310292402968"          # в приветственном тексте
EMOJI_BELL = "5773677501825945508"          # в приветственном тексте
EMOJI_CATEGORY_TEXT = "5890883384057533697" # в тексте "Выберите категорию"

# Иконки на кнопках нижней панели (icon_custom_emoji_id — премиум-иконка без обычного эмодзи в тексте)
EMOJI_CATEGORY_BTN = "5890883384057533697"      # кнопка "Категория" (красная)
EMOJI_PROFILE_BTN = "5258508428212445001"       # кнопка "Профиль"
EMOJI_CHANNEL_BTN = "5258513401784573443"       # кнопка "Наш канал"
EMOJI_AGREEMENT_BTN = "5890883384057533697"     # кнопка "Соглашение"
EMOJI_HELP_BTN = "5454386656628991407"          # кнопка "Помощь"

EMOJI_OXIDE_BTN = "5294524383279198295"         # кнопка "Oxide" (зелёная)
EMOJI_ANDROID_NOROOT_BTN = "5280709788475360932"  # кнопка "Android-noRoot"
EMOJI_CRY4ME_BTN = "5283235624382406181"        # кнопка "cry4me"
EMOJI_CRY4ME_1D_BTN = "5231449120635370684"     # кнопка "cry4me 1D — <цена>"

EMOJI_ADDKEY = "5416041192905265756"   # 🔑 в шапке экрана "Добавить ключи" в админке

DB_PATH = "shop.db"

# ======================= БАЗА ДАННЫХ =======================


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key_value TEXT NOT NULL,
            is_used INTEGER DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            price TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            receipt_file_id TEXT,
            receipt_type TEXT,
            key_value TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER NOT NULL,
            username TEXT,
            rating INTEGER NOT NULL,
            text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    conn.close()


def get_setting(key: str, default=None):
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_admin_chat_id() -> int:
    # Кто последним успешно ввёл пароль в /admin — тот и получает уведомления о чеках.
    stored = get_setting("admin_id")
    return int(stored) if stored else ADMIN_ID


def is_admin(user_id: int) -> bool:
    return user_id == get_admin_chat_id() or user_id == ADMIN_ID


# ======================= ПОМОЩНИК ДЛЯ ПРЕМИУМ-ЭМОДЗИ =======================


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def emoji_entity(text: str, placeholder: str, emoji_id: str) -> MessageEntity:
    idx = text.index(placeholder)
    offset = utf16_len(text[:idx])
    length = utf16_len(placeholder)
    return MessageEntity(
        type="custom_emoji", offset=offset, length=length, custom_emoji_id=emoji_id
    )


# ======================= FSM СОСТОЯНИЯ =======================


class AdminStates(StatesGroup):
    waiting_password = State()
    waiting_add_key = State()
    waiting_broadcast = State()
    waiting_new_price = State()


ADD_KEY_CATEGORY_KEY = "add_key_category"  # ключ в FSM data — для какой composite-категории сейчас добавляем ключи


class ReviewStates(StatesGroup):
    waiting_text = State()


# ======================= КЛАВИАТУРЫ =======================

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Категория", icon_custom_emoji_id=EMOJI_CATEGORY_BTN, style="danger")],
        [
            KeyboardButton(text="Профиль", icon_custom_emoji_id=EMOJI_PROFILE_BTN),
            KeyboardButton(text="Наш канал", icon_custom_emoji_id=EMOJI_CHANNEL_BTN),
        ],
        [
            KeyboardButton(text="Соглашение", icon_custom_emoji_id=EMOJI_AGREEMENT_BTN),
            KeyboardButton(text="Помощь", icon_custom_emoji_id=EMOJI_HELP_BTN),
        ],
    ],
    resize_keyboard=True,
)

# Подменю "Категория". Стиль кнопки (цвет) есть только у ReplyKeyboardButton,
# поэтому список категорий сделан отдельной нижней панелью, а не инлайн-кнопками.
CATEGORY_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Oxide", icon_custom_emoji_id=EMOJI_OXIDE_BTN, style="success")],
        [KeyboardButton(text="Android-noRoot", icon_custom_emoji_id=EMOJI_ANDROID_NOROOT_BTN)],
        [KeyboardButton(text="cry4me", icon_custom_emoji_id=EMOJI_CRY4ME_BTN)],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True,
)


def build_cry4me_kb() -> ReplyKeyboardMarkup:
    """Собирается динамически, т.к. цены можно менять в /admin → 💰 Цены."""
    price_1d = get_variant_price("cry4me", "1d")
    price_7d = get_variant_price("cry4me", "7d")
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"cry4me 1D — {price_1d}", icon_custom_emoji_id=EMOJI_CRY4ME_1D_BTN)],
            [KeyboardButton(text=f"cry4me 7D — {price_7d}")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def rating_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐" * n, callback_data=f"rate_{order_id}_{n}")
                for n in range(1, 6)
            ]
        ]
    )


# ======================= ТОВАРЫ / КАТЕГОРИИ =======================
#
# Два вида категорий:
#   type="product" — категория с вариантами покупки (у каждого варианта своя
#                     цена и свой пул ключей в БД).
#   type="info"     — информационная категория без покупки (просто текст).
#
# ВАЖНО: Oxide и Android-noRoot добавлены как заглушки типа "info" —
# впишите их реальное описание в поле "text" ниже.

CATEGORIES = {
    "oxide": {
        "type": "info",
        "text": "Здесь будет описание категории Oxide. Впишите свой текст.",
    },
    "android_noroot": {
        "type": "info",
        "text": "Здесь будет описание категории Android-noRoot. Впишите свой текст.",
    },
    "cry4me": {
        "type": "product",
        "variants": {
            # composite-ключ категории в БД (keys.category / orders.category) = "cry4me_1d" / "cry4me_7d"
            "1d": {"label": "cry4me 1D", "price_key": "price_cry4me_1d", "default_price": "160 руб"},
            "7d": {"label": "cry4me 7D", "price_key": "price_cry4me_7d", "default_price": "750 руб"},
        },
    },
}


def composite_key(category_key: str, variant_key: str) -> str:
    """cry4me + 1d -> 'cry4me_1d'; google_account + main -> 'google_account_main'."""
    return f"{category_key}_{variant_key}"


def get_variant_price(category_key: str, variant_key: str) -> str:
    v = CATEGORIES[category_key]["variants"][variant_key]
    return get_setting(v["price_key"], v["default_price"])


def find_variant(comp_key: str):
    """comp_key -> (category_key, variant_key, category, variant) или (None, None, None, None)."""
    for cat_key, cat in CATEGORIES.items():
        if cat["type"] != "product":
            continue
        for var_key in cat["variants"]:
            if composite_key(cat_key, var_key) == comp_key:
                return cat_key, var_key, cat, cat["variants"][var_key]
    return None, None, None, None


async def fulfill_order(bot: Bot, order_id: int) -> bool:
    """Пытается выдать ключ/аккаунт по заказу. Возвращает True, если выдано."""
    conn = db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order or order["status"] != "awaiting_confirmation":
        conn.close()
        return False

    key_row = conn.execute(
        "SELECT * FROM keys WHERE category = ? AND is_used = 0 LIMIT 1", (order["category"],)
    ).fetchone()
    if not key_row:
        conn.close()
        return False

    conn.execute("UPDATE keys SET is_used = 1 WHERE id = ?", (key_row["id"],))
    conn.execute(
        "UPDATE orders SET status = 'completed', key_value = ? WHERE id = ?",
        (key_row["key_value"], order_id),
    )
    conn.commit()
    conn.close()

    # Google-аккаунты храним в формате "логин:пароль" — показываем красиво.
    if order["category"].startswith("google_account") and ":" in key_row["key_value"]:
        login, password = key_row["key_value"].split(":", 1)
        delivery_text = (
            "✅ Оплата подтверждена!\n\n"
            f"📧 Логин: <code>{login}</code>\n"
            f"🔑 Пароль: <code>{password}</code>"
        )
    else:
        delivery_text = f"✅ Оплата подтверждена!\nВаш ключ: <code>{key_row['key_value']}</code>"

    await bot.send_message(order["user_id"], delivery_text, parse_mode="HTML")

    private_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="вот приватка там все файлы", url=PRIVATE_FILES_LINK)]
        ]
    )
    await bot.send_message(order["user_id"], "📁 Доступ к файлам:", reply_markup=private_kb)

    await bot.send_message(
        order["user_id"],
        "🙏 Спасибо за покупку! Оцените нас от 1 до 5 звёзд:",
        reply_markup=rating_kb(order_id),
    )
    return True


ADMIN_MENU = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Чеки", callback_data="admin_receipts")],
        [InlineKeyboardButton(text="➕ Добавить ключи", callback_data="admin_add_keys")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="admin_prices")],
        [InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders")],
        [InlineKeyboardButton(text="📢 Сделать объявление", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📝 Отзывы", callback_data="admin_reviews")],
    ]
)

# ======================= ПОЛЬЗОВАТЕЛЬСКИЙ РОУТЕР =======================

router = Router()


def agreement_text_and_kb():
    text = "Пользовательское соглашение и политика конфиденциальности:"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Пользовательское соглашение", url=AGREEMENT_LINK),
                InlineKeyboardButton(text="📄 Политика конфиденциальности", url=PRIVACY_LINK),
            ],
            [InlineKeyboardButton(text="✅ Прочитал", callback_data="agree_read")],
        ]
    )
    return text, kb


def welcome_text_and_entities():
    text = (
        "🎁 Привет!\n\n"
        "Спасибо, что решили воспользоваться нашим магазином.\n\n"
        "🔔 Если у вас есть вопросы или проблемы с товаром — напишите в поддержку.\n\n"
        "Перед началом использования бота ознакомьтесь с политикой конфиденциальности "
        "и пользовательским соглашением."
    )
    entities = [
        emoji_entity(text, "🎁", EMOJI_GIFT),
        emoji_entity(text, "🔔", EMOJI_BELL),
    ]
    return text, entities


@router.message(CommandStart())
async def cmd_start(message: Message):
    conn = db()
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    conn.commit()
    conn.close()

    # Первым сообщением — соглашение и политика конфиденциальности.
    # Приветствие (и нижняя панель) появится только после нажатия "✅ Прочитал".
    text, kb = agreement_text_and_kb()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "agree_read")
async def agree_read(callback: CallbackQuery):
    text, entities = welcome_text_and_entities()
    await callback.message.answer(text, entities=entities, reply_markup=MAIN_KB)
    await callback.answer()


@router.message(F.text == "Категория")
async def show_categories(message: Message):
    text = "🛍 Выберите категорию:"
    entities = [emoji_entity(text, "🛍", EMOJI_CATEGORY_TEXT)]
    await message.answer(text, entities=entities, reply_markup=CATEGORY_KB)


@router.message(F.text == "⬅️ Назад")
async def go_back(message: Message):
    await message.answer("Главное меню:", reply_markup=MAIN_KB)


@router.message(F.text == "Oxide")
async def category_oxide(message: Message):
    await message.answer(CATEGORIES["oxide"]["text"])


@router.message(F.text == "Android-noRoot")
async def category_android_noroot(message: Message):
    await message.answer(CATEGORIES["android_noroot"]["text"])


@router.message(F.text == "cry4me")
async def category_cry4me(message: Message):
    await message.answer("Выберите вариант:", reply_markup=build_cry4me_kb())


@router.message(F.text == "Профиль")
async def profile(message: Message):
    conn = db()
    count = conn.execute(
        "SELECT COUNT(*) as c FROM orders WHERE user_id = ? AND status = 'completed'",
        (message.from_user.id,),
    ).fetchone()["c"]
    conn.close()
    await message.answer(f"👤 Ваш профиль\n\nКуплено товаров: {count}")


@router.message(F.text == "Наш канал")
async def our_channel(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть канал", url=CHANNEL_LINK)]]
    )
    await message.answer("Наш канал:", reply_markup=kb)


@router.message(F.text == "Соглашение")
async def agreement_and_privacy(message: Message):
    text, kb = agreement_text_and_kb()
    await message.answer(text, reply_markup=kb)


@router.message(F.text == "Помощь")
async def help_message(message: Message):
    await message.answer(f"Если у вас возникла проблема напишите нам {SUPPORT_USERNAME}")


async def start_purchase(message: Message, cat_key: str, var_key: str):
    price = get_variant_price(cat_key, var_key)
    comp = composite_key(cat_key, var_key)
    user_id = message.from_user.id
    conn = db()
    conn.execute(
        "INSERT INTO orders (user_id, category, price, status) VALUES (?, ?, ?, 'pending')",
        (user_id, comp, price),
    )
    conn.commit()
    conn.close()

    text = (
        f"Переведите на данные реквизиты:\n\n"
        f"💳 {CARD_NUMBER}\n\n"
        f"После оплаты пришлите сюда чек (фото или файл)."
    )
    await message.answer(text, reply_markup=MAIN_KB)


@router.message(F.text.startswith("cry4me 1D"))
async def buy_cry4me_1d(message: Message):
    await start_purchase(message, "cry4me", "1d")


@router.message(F.text.startswith("cry4me 7D"))
async def buy_cry4me_7d(message: Message):
    await start_purchase(message, "cry4me", "7d")


@router.message(F.photo | F.document)
async def receive_receipt(message: Message):
    user_id = message.from_user.id
    conn = db()
    order = conn.execute(
        "SELECT * FROM orders WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if not order:
        conn.close()
        return  # нет ожидающего заказа — игнорируем

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    receipt_type = "photo" if message.photo else "document"
    conn.execute(
        "UPDATE orders SET receipt_file_id = ?, receipt_type = ?, status = 'awaiting_confirmation' WHERE id = ?",
        (file_id, receipt_type, order["id"]),
    )
    conn.commit()
    conn.close()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{order['id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order['id']}"),
            ]
        ]
    )
    caption = (
        f"🧾 Новый чек по заказу #{order['id']}\n"
        f"Пользователь: {user_id}\n"
        f"Категория: {order['category']}\n"
        f"Сумма: {order['price']}"
    )
    if message.photo:
        await message.bot.send_photo(get_admin_chat_id(), file_id, caption=caption, reply_markup=kb)
    else:
        await message.bot.send_document(get_admin_chat_id(), file_id, caption=caption, reply_markup=kb)

    await message.answer("⏳ Подождите, пока подтвердится оплата")


@router.callback_query(F.data.startswith("approve_"))
async def approve_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return

    order_id = int(callback.data.split("_", 1)[1])
    conn = db()
    order = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()
    if not order or order["status"] != "awaiting_confirmation":
        await callback.answer("Заказ уже обработан", show_alert=True)
        return

    ok = await fulfill_order(callback.bot, order_id)
    if not ok:
        await callback.answer("Нет свободных ключей! Добавьте через /admin", show_alert=True)
        return

    if callback.message.caption:
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ Подтверждено")
    await callback.answer("Ключ выдан")


@router.callback_query(F.data.startswith("rate_"))
async def rate_order(callback: CallbackQuery, state: FSMContext):
    _, order_id, rating = callback.data.split("_")
    await state.update_data(review_order_id=int(order_id), review_rating=int(rating))
    await state.set_state(ReviewStates.waiting_text)
    await callback.message.edit_text(
        f"Ваша оценка: {'⭐' * int(rating)}\n\nНапишите текст отзыва:"
    )
    await callback.answer()


@router.message(ReviewStates.waiting_text)
async def save_review(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("review_order_id")
    rating = data.get("review_rating", 5)
    await state.clear()

    username = (
        f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    )

    conn = db()
    conn.execute(
        "INSERT INTO reviews (order_id, user_id, username, rating, text) VALUES (?, ?, ?, ?, ?)",
        (order_id, message.from_user.id, username, rating, message.text),
    )
    conn.commit()
    conn.close()

    await message.answer("Спасибо за отзыв! ❤️")


@router.callback_query(F.data.startswith("reject_"))
async def reject_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return

    order_id = int(callback.data.split("_", 1)[1])
    conn = db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order and order["status"] == "awaiting_confirmation":
        conn.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        conn.commit()
    conn.close()

    if order:
        await callback.bot.send_message(order["user_id"], "❌ Чек не подтверждён. Свяжитесь с поддержкой.")
    if callback.message.caption:
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ Отклонено")
    await callback.answer("Заказ отклонён")


# ======================= АДМИН-РОУТЕР =======================

admin_router = Router()


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await message.answer("Введите пароль:")
    await state.set_state(AdminStates.waiting_password)


@admin_router.message(AdminStates.waiting_password)
async def check_password(message: Message, state: FSMContext):
    if message.text == ADMIN_PASSWORD:
        set_setting("admin_id", str(message.from_user.id))
        await state.clear()
        await message.answer("Добро пожаловать в админ-панель:", reply_markup=ADMIN_MENU)
    else:
        await message.answer("Неверный пароль.")
        await state.clear()


@admin_router.callback_query(F.data == "admin_receipts")
async def admin_receipts(callback: CallbackQuery):
    conn = db()
    orders = conn.execute(
        "SELECT * FROM orders WHERE status = 'awaiting_confirmation' ORDER BY id"
    ).fetchall()
    conn.close()

    if not orders:
        await callback.message.answer("Нет чеков на проверке.")
        await callback.answer()
        return

    for order in orders:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{order['id']}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order['id']}"),
                ]
            ]
        )
        caption = (
            f"🧾 Заказ #{order['id']}\n"
            f"Пользователь: {order['user_id']}\n"
            f"Категория: {order['category']}\n"
            f"Сумма: {order['price']}"
        )
        if order["receipt_type"] == "photo":
            await callback.message.answer_photo(order["receipt_file_id"], caption=caption, reply_markup=kb)
        elif order["receipt_type"] == "document":
            await callback.message.answer_document(order["receipt_file_id"], caption=caption, reply_markup=kb)
        else:
            await callback.message.answer(caption, reply_markup=kb)

    await callback.answer()


@admin_router.callback_query(F.data == "admin_add_keys")
async def admin_add_keys_start(callback: CallbackQuery):
    kb_rows = []
    for cat_key, cat in CATEGORIES.items():
        if cat["type"] != "product":
            continue
        for var_key, var in cat["variants"].items():
            comp = composite_key(cat_key, var_key)
            kb_rows.append(
                [InlineKeyboardButton(text=f"➕ {var['label']}", callback_data=f"addkey_{comp}")]
            )
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    text = "🔑 В какую категорию добавить ключи?"
    entities = [emoji_entity(text, "🔑", EMOJI_ADDKEY)]
    await callback.message.answer(text, entities=entities, reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("addkey_"))
async def admin_add_keys_pick_category(callback: CallbackQuery, state: FSMContext):
    comp = callback.data.split("_", 1)[1]
    cat_key, var_key, cat, var = find_variant(comp)
    if not cat_key:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    await state.update_data(**{ADD_KEY_CATEGORY_KEY: comp})
    await state.set_state(AdminStates.waiting_add_key)

    if comp.startswith("google_account"):
        hint = "Пришлите аккаунты, каждый с новой строки, в формате логин:пароль:\n\nexample@gmail.com:parol123"
    else:
        hint = "Пришлите ключи, каждый с новой строки:\n\nAAAA-BBBB-CCCC"
    await callback.message.answer(f"Добавление ключей — «{var['label']}»\n\n{hint}")
    await callback.answer()


@admin_router.message(AdminStates.waiting_add_key)
async def admin_add_keys_save(message: Message, state: FSMContext):
    data = await state.get_data()
    category = data.get(ADD_KEY_CATEGORY_KEY)
    await state.clear()

    if not category:
        await message.answer("Сессия добавления ключей истекла. Начните заново через «➕ Добавить ключи».")
        return

    lines = [line.strip() for line in (message.text or "").splitlines() if line.strip()]

    conn = db()
    added = 0
    for key_value in lines:
        conn.execute(
            "INSERT INTO keys (category, key_value) VALUES (?, ?)", (category, key_value)
        )
        added += 1
    conn.commit()
    conn.close()

    result = f"Добавлено: {added}"

    # Авто-выдача: если кого-то уже одобрили, но раньше не хватало ключей/аккаунтов — выдаём сейчас
    conn = db()
    waiting = conn.execute(
        "SELECT id FROM orders WHERE status = 'awaiting_confirmation'"
    ).fetchall()
    conn.close()
    auto_issued = 0
    for row in waiting:
        if await fulfill_order(message.bot, row["id"]):
            auto_issued += 1
    if auto_issued:
        result += f"\n🔑 Автоматически выдано по ожидавшим заказам: {auto_issued}"

    await message.answer(result)


@admin_router.callback_query(F.data == "admin_prices")
async def admin_prices(callback: CallbackQuery):
    kb_rows = []
    for cat_key, cat in CATEGORIES.items():
        if cat["type"] != "product":
            continue
        for var_key, var in cat["variants"].items():
            comp = composite_key(cat_key, var_key)
            price = get_variant_price(cat_key, var_key)
            kb_rows.append(
                [InlineKeyboardButton(text=f"{var['label']} — {price}", callback_data=f"editprice_{comp}")]
            )
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await callback.message.answer("💰 Выберите товар, чтобы изменить цену:", reply_markup=kb)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("editprice_"))
async def admin_edit_price_start(callback: CallbackQuery, state: FSMContext):
    comp = callback.data.split("_", 1)[1]
    cat_key, var_key, cat, var = find_variant(comp)
    if not cat_key:
        await callback.answer("Товар не найден", show_alert=True)
        return
    await state.update_data(price_key=var["price_key"], price_label=var["label"])
    await state.set_state(AdminStates.waiting_new_price)
    await callback.message.answer(f"Введите новую цену для «{var['label']}» (например: 200 руб):")
    await callback.answer()


@admin_router.message(AdminStates.waiting_new_price)
async def admin_edit_price_save(message: Message, state: FSMContext):
    data = await state.get_data()
    price_key = data.get("price_key")
    label = data.get("price_label", "товар")
    await state.clear()

    new_price = (message.text or "").strip()
    if not new_price:
        await message.answer("Цена не может быть пустой.")
        return

    set_setting(price_key, new_price)
    await message.answer(f"Готово! Новая цена для «{label}»: {new_price}")


@admin_router.callback_query(F.data == "admin_orders")
async def admin_orders(callback: CallbackQuery):
    conn = db()
    orders = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()

    if not orders:
        await callback.message.answer("Заказов пока нет.")
    else:
        lines = [
            f"#{o['id']} | user {o['user_id']} | {o['category']} | {o['price']} | {o['status']}"
            for o in orders
        ]
        await callback.message.answer("📦 Последние заказы:\n\n" + "\n".join(lines))
    await callback.answer()


@admin_router.callback_query(F.data == "admin_reviews")
async def admin_reviews(callback: CallbackQuery):
    conn = db()
    reviews = conn.execute("SELECT * FROM reviews ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()

    if not reviews:
        await callback.message.answer("Отзывов пока нет.")
        await callback.answer()
        return

    for r in reviews:
        stars = "⭐" * r["rating"] + "☆" * (5 - r["rating"])
        order_part = f" (заказ #{r['order_id']})" if r["order_id"] else ""
        text = (
            f"📝 Отзыв{order_part}\n\n"
            f"{stars}\n\n"
            f"{r['text'] or '—'}\n\n"
            f"— {r['username']}"
        )
        await callback.message.answer(text)

    await callback.answer()


@admin_router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Пришлите текст объявления для рассылки всем пользователям:")
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.answer()


@admin_router.message(AdminStates.waiting_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext):
    conn = db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    await state.clear()

    sent, failed = 0, 0
    for u in users:
        try:
            await message.bot.send_message(u["user_id"], message.text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # чтобы не упереться в лимиты Telegram

    await message.answer(f"Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")


# ======================= ЗАПУСК =======================


async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)  # админ-роутер первым — важно для приоритета FSM
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
