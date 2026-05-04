from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import main_menu_keyboard

router = Router()


MAIN_MENU_TEXT = (
    "GitNotifyBot\n\n"
    "Отслеживаю обновления GitHub-репозиториев и присылаю краткие сводки.\n\n"
    "Сейчас доступен стартовый интерфейс. Добавление подписок, GitHub-проверки и LLM-сводки "
    "будут включены следующими инкрементами."
)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("menu"))
async def menu(message: Message) -> None:
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:add")
async def add_repository(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Добавление репозитория появится следующим шагом.\n\n"
            "Планируемый формат: отправь GitHub URL или owner/repo, затем выбери Releases или File."
        )


@router.callback_query(F.data == "menu:subscriptions")
async def subscriptions(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Список подписок появится после реализации subscription flow."
        )


@router.callback_query(F.data == "menu:check")
async def check_now(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer("Ручная проверка появится вместе с worker pipeline.")


@router.callback_query(F.data == "menu:settings")
async def settings(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Настройки summary появятся следующим инкрементом: язык, стиль и пожелания."
        )


@router.callback_query(F.data == "menu:help")
async def help_message(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "GitNotifyBot будет отслеживать публичные GitHub-репозитории в режимах Releases и File."
        )
