from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

REPLY_BTN_ADD = "➕ Добавить репозиторий"
REPLY_BTN_LIST = "📋 Мои подписки"
REPLY_BTN_CHECK = "🔍 Проверить сейчас"
REPLY_BTN_SETTINGS = "⚙️ Настройки"
REPLY_BTN_HELP = "❓ Помощь"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=REPLY_BTN_ADD)],
            [
                KeyboardButton(text=REPLY_BTN_LIST),
                KeyboardButton(text=REPLY_BTN_CHECK),
            ],
            [
                KeyboardButton(text=REPLY_BTN_SETTINGS),
                KeyboardButton(text=REPLY_BTN_HELP),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери действие или используй кнопки ниже",
    )


def subscriptions_list_keyboard(
    items: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"❌ {full_name}",
                callback_data=f"sub:del:{subscription_id}",
            )
        ]
        for subscription_id, full_name in items
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard(language: str, style: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🌍 Язык: {language}", callback_data="settings:lang")],
            [InlineKeyboardButton(text=f"🎯 Стиль: {style}", callback_data="settings:style")],
            [InlineKeyboardButton(text="📝 Пожелания", callback_data="settings:prefs")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:back")],
        ]
    )


def settings_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 ru", callback_data="settings:lang:ru"),
                InlineKeyboardButton(text="🇬🇧 en", callback_data="settings:lang:en"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:back")],
        ]
    )


def settings_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Кратко",
                    callback_data="settings:style:short_technical",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Подробно",
                    callback_data="settings:style:detailed",
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:back")],
        ]
    )


def settings_preferences_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Очистить", callback_data="settings:prefs:clear")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:back")],
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить репозиторий", callback_data="menu:add")],
            [InlineKeyboardButton(text="📋 Мои подписки", callback_data="menu:subscriptions")],
            [InlineKeyboardButton(text="🔍 Проверить сейчас", callback_data="menu:check")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
        ]
    )


def subscription_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Releases", callback_data="add:mode:releases")],
            [InlineKeyboardButton(text="File", callback_data="add:mode:file")],
            [InlineKeyboardButton(text="Отмена", callback_data="add:cancel")],
        ]
    )
