from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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
