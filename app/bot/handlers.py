from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.subscriptions import SqlAlchemySubscriptionStore, add_release_subscription
from app.bot.keyboards import main_menu_keyboard, subscription_mode_keyboard
from app.domain.github import GitHubRepositoryRef, parse_github_repository
from app.integrations.github import GitHubApiError, GitHubClient, GitHubNotFoundError

router = Router()


MAIN_MENU_TEXT = (
    "GitNotifyBot\n\n"
    "Отслеживаю обновления GitHub-репозиториев и присылаю краткие сводки.\n\n"
    "Добавь публичный репозиторий через кнопку ниже. Сейчас доступен режим Releases; "
    "режим File появится следующим инкрементом."
)


class AddRepositoryFlow(StatesGroup):
    waiting_for_repository = State()
    waiting_for_mode = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:add")
async def add_repository(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddRepositoryFlow.waiting_for_repository)
    if callback.message:
        await callback.message.answer(
            "Отправь GitHub URL или owner/repo.\n\n"
            "Например: https://github.com/owner/repo или owner/repo"
        )


@router.message(AddRepositoryFlow.waiting_for_repository)
async def receive_repository(
    message: Message,
    state: FSMContext,
    github_client: GitHubClient,
) -> None:
    if not message.text:
        await message.answer("Отправь текстом GitHub URL или owner/repo.")
        return

    try:
        repository_ref = parse_github_repository(message.text)
        github_repository = await github_client.get_repository(repository_ref)
    except ValueError:
        await message.answer(
            "Не получилось разобрать репозиторий. Формат: owner/repo или GitHub URL."
        )
        return
    except GitHubNotFoundError:
        await message.answer("GitHub не нашел такой публичный репозиторий.")
        return
    except GitHubApiError:
        await message.answer("GitHub API сейчас не ответил корректно. Попробуй позже.")
        return

    await state.update_data(
        repo_owner=github_repository.owner,
        repo_name=github_repository.name,
        repo_full_name=github_repository.full_name,
    )
    await state.set_state(AddRepositoryFlow.waiting_for_mode)
    await message.answer(
        f"Репозиторий найден: {github_repository.full_name}\n\nВыбери режим отслеживания:",
        reply_markup=subscription_mode_keyboard(),
    )


@router.callback_query(AddRepositoryFlow.waiting_for_mode, F.data == "add:mode:releases")
async def add_releases_subscription(
    callback: CallbackQuery,
    state: FSMContext,
    github_client: GitHubClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    user = callback.from_user
    chat = callback.message.chat
    data = await state.get_data()
    repo_owner = data.get("repo_owner")
    repo_name = data.get("repo_name")
    if not isinstance(repo_owner, str) or not isinstance(repo_name, str):
        await state.clear()
        await callback.message.answer(
            "Сессия добавления устарела. Нажми “Добавить репозиторий” еще раз."
        )
        return

    try:
        async with session_factory() as session:
            async with session.begin():
                result = await add_release_subscription(
                    store=SqlAlchemySubscriptionStore(session),
                    github_client=github_client,
                    repository_ref=GitHubRepositoryRef(owner=repo_owner, name=repo_name),
                    telegram_chat_id=chat.id,
                    chat_type=chat.type,
                    chat_title=chat.title,
                    telegram_user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code,
                )
    except GitHubNotFoundError:
        await callback.message.answer(
            "GitHub больше не находит этот репозиторий. Попробуй добавить заново."
        )
        return
    except GitHubApiError:
        await callback.message.answer("GitHub API сейчас не ответил корректно. Попробуй позже.")
        return

    await state.clear()
    baseline = result.latest_release_tag or "релизы пока отсутствуют"
    if result.created:
        await callback.message.answer(
            "Подписка добавлена.\n\n"
            f"Репозиторий: {result.repository_full_name}\n"
            f"Режим: Releases\n"
            f"Baseline: {baseline}"
        )
    else:
        await callback.message.answer(
            f"Подписка на Releases для {result.repository_full_name} уже существует."
        )


@router.callback_query(AddRepositoryFlow.waiting_for_mode, F.data == "add:mode:file")
async def add_file_subscription_placeholder(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Режим File пока в разработке. Сейчас можно добавить подписку в режиме Releases."
        )


@router.callback_query(F.data == "add:cancel")
async def cancel_add_repository(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.answer(
            "Добавление репозитория отменено.",
            reply_markup=main_menu_keyboard(),
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
