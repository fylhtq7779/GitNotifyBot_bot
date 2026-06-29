from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.chat_settings import (
    MAX_PREFERENCES_LENGTH,
    SqlAlchemyChatSettingsStore,
    get_chat_settings,
    set_chat_summary_language,
    set_chat_summary_preferences,
    set_chat_summary_style,
)
from app.application.subscriptions import (
    SqlAlchemySubscriptionStore,
    SubscriptionListItem,
    add_file_subscription,
    add_release_subscription,
    delete_chat_subscription,
    list_chat_subscriptions,
    reschedule_chat_subscriptions_now,
)
from app.bot.keyboards import (
    REPLY_BTN_ADD,
    REPLY_BTN_CHECK,
    REPLY_BTN_HELP,
    REPLY_BTN_LIST,
    REPLY_BTN_SETTINGS,
    main_menu_keyboard,
    main_reply_keyboard,
    settings_keyboard,
    settings_language_keyboard,
    settings_preferences_keyboard,
    settings_style_keyboard,
    subscription_mode_keyboard,
    subscriptions_list_keyboard,
)
from app.domain.github import GitHubRepositoryRef, parse_github_repository
from app.integrations.github import GitHubApiError, GitHubClient, GitHubNotFoundError

router = Router()


MAIN_MENU_TEXT = (
    "GitNotifyBot\n\n"
    "Отслеживаю обновления GitHub-репозиториев и присылаю краткие сводки.\n\n"
    "Поддерживаются режимы Releases и File. Сводки готовятся LLM на выбранном языке."
)


class AddRepositoryFlow(StatesGroup):
    waiting_for_repository = State()
    waiting_for_mode = State()
    waiting_for_file_path = State()


class SettingsFlow(StatesGroup):
    waiting_for_preferences = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Клавиатура меню всегда внизу.", reply_markup=main_reply_keyboard())
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.message(Command("menu"))
async def menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


@router.message(F.text == REPLY_BTN_ADD)
async def reply_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddRepositoryFlow.waiting_for_repository)
    await message.answer(
        "Отправь GitHub URL или owner/repo.\n\n"
        "Например: https://github.com/owner/repo или owner/repo"
    )


@router.message(F.text == REPLY_BTN_LIST)
async def reply_list(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    chat_id = message.chat.id
    async with session_factory() as session:
        async with session.begin():
            items = await list_chat_subscriptions(
                store=SqlAlchemySubscriptionStore(session),
                telegram_chat_id=chat_id,
            )
    if not items:
        await message.answer(
            "У тебя пока нет подписок. Нажми «Добавить репозиторий».",
            reply_markup=main_menu_keyboard(),
        )
        return
    keyboard = subscriptions_list_keyboard(
        [(item.subscription_id, item.repository_full_name) for item in items]
    )
    await message.answer(_format_subscription_list(items), reply_markup=keyboard)


@router.message(F.text == REPLY_BTN_CHECK)
async def reply_check(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    chat_id = message.chat.id
    async with session_factory() as session:
        async with session.begin():
            count = await reschedule_chat_subscriptions_now(
                store=SqlAlchemySubscriptionStore(session),
                telegram_chat_id=chat_id,
            )
    if count == 0:
        await message.answer(
            "Активных подписок нет, проверять нечего.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await message.answer(
        f"Поставил в очередь {count} подписок. "
        "Уведомления придут после ближайшего цикла worker'а (до минуты)."
    )


@router.message(F.text == REPLY_BTN_SETTINGS)
async def reply_settings(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.clear()
    await _show_settings_overview(message, session_factory)


@router.message(F.text == REPLY_BTN_HELP)
async def reply_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


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
async def request_file_path(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(AddRepositoryFlow.waiting_for_file_path)
    await callback.message.answer(
        "Отправь путь к файлу на default branch.\n\nНапример: README.md или src/app.py"
    )


@router.message(AddRepositoryFlow.waiting_for_file_path)
async def receive_file_path(
    message: Message,
    state: FSMContext,
    github_client: GitHubClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.text:
        await message.answer("Отправь путь к файлу текстом.")
        return

    data = await state.get_data()
    repo_owner = data.get("repo_owner")
    repo_name = data.get("repo_name")
    if not isinstance(repo_owner, str) or not isinstance(repo_name, str):
        await state.clear()
        await message.answer(
            "Сессия добавления устарела. Нажми “Добавить репозиторий” ещё раз.",
            reply_markup=main_menu_keyboard(),
        )
        return

    user = message.from_user
    if user is None:
        await state.clear()
        await message.answer("Не получилось определить пользователя Telegram.")
        return

    chat = message.chat
    file_path = message.text.strip().lstrip("/")
    if not file_path:
        await message.answer("Путь к файлу не может быть пустым.")
        return

    try:
        async with session_factory() as session:
            async with session.begin():
                result = await add_file_subscription(
                    store=SqlAlchemySubscriptionStore(session),
                    github_client=github_client,
                    repository_ref=GitHubRepositoryRef(owner=repo_owner, name=repo_name),
                    file_path=file_path,
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
        await message.answer(
            "Файл не найден на default branch. Проверь путь и отправь ещё раз."
        )
        return
    except GitHubApiError as exc:
        await message.answer(f"GitHub API не ответил корректно: {exc}")
        return
    except ValueError as exc:
        await message.answer(f"Не получилось добавить файл: {exc}")
        return

    await state.clear()
    if result.created:
        await message.answer(
            "Подписка добавлена.\n\n"
            f"Репозиторий: {result.repository_full_name}\n"
            f"Режим: File\n"
            f"Branch: {result.branch}\n"
            f"Файл: {result.file_path}\n"
            f"Baseline sha: {result.file_sha[:7]}",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            f"Подписка на {result.repository_full_name}:{result.file_path} уже существует.",
            reply_markup=main_menu_keyboard(),
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
async def subscriptions(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    chat_id = callback.message.chat.id
    async with session_factory() as session:
        async with session.begin():
            items = await list_chat_subscriptions(
                store=SqlAlchemySubscriptionStore(session),
                telegram_chat_id=chat_id,
            )
    if not items:
        await callback.message.answer(
            "У тебя пока нет подписок. Нажми “Добавить репозиторий” в главном меню.",
            reply_markup=main_menu_keyboard(),
        )
        return
    text = _format_subscription_list(items)
    keyboard = subscriptions_list_keyboard(
        [(item.subscription_id, item.repository_full_name) for item in items]
    )
    await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("sub:del:"))
async def delete_subscription(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    try:
        subscription_id = int(callback.data.removeprefix("sub:del:"))
    except ValueError:
        await callback.message.answer("Не получилось разобрать команду удаления.")
        return

    chat_id = callback.message.chat.id
    async with session_factory() as session:
        async with session.begin():
            store = SqlAlchemySubscriptionStore(session)
            removed_full_name = await delete_chat_subscription(
                store=store,
                telegram_chat_id=chat_id,
                subscription_id=subscription_id,
            )
            if removed_full_name is None:
                await callback.message.answer(
                    "Подписка уже удалена или не принадлежит этому чату."
                )
                return
            items = await list_chat_subscriptions(
                store=store,
                telegram_chat_id=chat_id,
            )
    if not items:
        await callback.message.answer(
            f"Подписка на {removed_full_name} удалена. Подписок больше нет.",
            reply_markup=main_menu_keyboard(),
        )
        return
    keyboard = subscriptions_list_keyboard(
        [(item.subscription_id, item.repository_full_name) for item in items]
    )
    await callback.message.answer(
        f"Подписка на {removed_full_name} удалена.\n\n"
        + _format_subscription_list(items),
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "menu:back")
async def menu_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


def _format_subscription_list(items: list[SubscriptionListItem]) -> str:
    lines = [f"📋 Мои подписки ({len(items)})", ""]
    for index, item in enumerate(items, start=1):
        last_seen = item.last_seen_tag or item.last_seen_file_sha
        last_seen_label = last_seen if last_seen else "не задано"
        last_checked = (
            _humanize_age(item.last_checked_at)
            if item.last_checked_at is not None
            else "ещё не проверяли"
        )
        lines.append(
            f"{index}. {item.repository_full_name} · {item.mode} · "
            f"{last_seen_label} · {last_checked}"
        )
    return "\n".join(lines)


def _humanize_age(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - moment
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return "только что"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч назад"
    days = hours // 24
    return f"{days} д назад"


@router.callback_query(F.data == "menu:check")
async def check_now(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    chat_id = callback.message.chat.id
    async with session_factory() as session:
        async with session.begin():
            count = await reschedule_chat_subscriptions_now(
                store=SqlAlchemySubscriptionStore(session),
                telegram_chat_id=chat_id,
            )
    if count == 0:
        await callback.message.answer(
            "Активных подписок нет, проверять нечего.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await callback.message.answer(
        f"Поставил в очередь {count} подписок. "
        "Уведомления придут после ближайшего цикла worker'а (до минуты)."
    )


@router.callback_query(F.data == "menu:settings")
async def settings(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    await _show_settings_overview(callback.message, session_factory)


@router.callback_query(F.data == "settings:back")
async def settings_back(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    await _show_settings_overview(callback.message, session_factory)


@router.callback_query(F.data == "settings:lang")
async def settings_lang(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери язык сводки:", reply_markup=settings_language_keyboard()
        )


@router.callback_query(F.data.in_({"settings:lang:ru", "settings:lang:en"}))
async def settings_lang_set(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    language = callback.data.removeprefix("settings:lang:")
    chat_id = callback.message.chat.id
    async with session_factory() as session:
        async with session.begin():
            ok = await set_chat_summary_language(
                store=SqlAlchemyChatSettingsStore(session),
                telegram_chat_id=chat_id,
                language=language,
            )
    if not ok:
        await callback.message.answer("Сначала добавь хотя бы одну подписку.")
        return
    await callback.message.answer(f"Язык сводки: {language}")
    await _show_settings_overview(callback.message, session_factory)


@router.callback_query(F.data == "settings:style")
async def settings_style(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Выбери стиль сводки:", reply_markup=settings_style_keyboard()
        )


@router.callback_query(
    F.data.in_({"settings:style:short_technical", "settings:style:detailed"})
)
async def settings_style_set(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await callback.answer()
    if callback.message is None or callback.data is None:
        return
    style = callback.data.removeprefix("settings:style:")
    chat_id = callback.message.chat.id
    async with session_factory() as session:
        async with session.begin():
            ok = await set_chat_summary_style(
                store=SqlAlchemyChatSettingsStore(session),
                telegram_chat_id=chat_id,
                style=style,
            )
    if not ok:
        await callback.message.answer("Сначала добавь хотя бы одну подписку.")
        return
    await callback.message.answer(f"Стиль сводки: {style}")
    await _show_settings_overview(callback.message, session_factory)


@router.callback_query(F.data == "settings:prefs")
async def settings_prefs(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.set_state(SettingsFlow.waiting_for_preferences)
    await callback.message.answer(
        "Отправь текстом, что важно подсветить в сводке. "
        f"Максимум {MAX_PREFERENCES_LENGTH} символов.\n\n"
        "Например: «выделяй breaking changes и изменения CLI».",
        reply_markup=settings_preferences_keyboard(),
    )


@router.callback_query(F.data == "settings:prefs:clear")
async def settings_prefs_clear(
    callback: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None:
        return
    chat_id = callback.message.chat.id
    async with session_factory() as session:
        async with session.begin():
            ok = await set_chat_summary_preferences(
                store=SqlAlchemyChatSettingsStore(session),
                telegram_chat_id=chat_id,
                preferences=None,
            )
    if not ok:
        await callback.message.answer("Сначала добавь хотя бы одну подписку.")
        return
    await callback.message.answer("Пожелания очищены.")
    await _show_settings_overview(callback.message, session_factory)


@router.message(SettingsFlow.waiting_for_preferences)
async def settings_prefs_set(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.text:
        await message.answer("Отправь пожелания текстом или нажми «Очистить».")
        return
    chat_id = message.chat.id
    try:
        async with session_factory() as session:
            async with session.begin():
                ok = await set_chat_summary_preferences(
                    store=SqlAlchemyChatSettingsStore(session),
                    telegram_chat_id=chat_id,
                    preferences=message.text,
                )
    except ValueError:
        await message.answer(
            f"Слишком длинно. Максимум {MAX_PREFERENCES_LENGTH} символов."
        )
        return
    await state.clear()
    if not ok:
        await message.answer("Сначала добавь хотя бы одну подписку.")
        return
    await message.answer("Пожелания сохранены.")
    await _show_settings_overview(message, session_factory)


async def _show_settings_overview(
    message: Message, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    chat_id = message.chat.id
    async with session_factory() as session:
        async with session.begin():
            current = await get_chat_settings(
                store=SqlAlchemyChatSettingsStore(session),
                telegram_chat_id=chat_id,
            )
    if current is None:
        await message.answer(
            "Настройки появятся после добавления первой подписки.",
            reply_markup=main_menu_keyboard(),
        )
        return
    preferences = current.preferences or "не заданы"
    await message.answer(
        "⚙️ Настройки сводки\n\n"
        f"Язык: {current.language}\n"
        f"Стиль: {current.style}\n"
        f"Пожелания: {preferences}",
        reply_markup=settings_keyboard(current.language, current.style),
    )


HELP_TEXT = (
    "GitNotifyBot отслеживает публичные GitHub-репозитории и присылает\n"
    "краткие сводки по их обновлениям прямо в этот чат.\n\n"
    "Команды:\n"
    "• /start, /menu: открыть главное меню\n\n"
    "Кнопки меню:\n"
    "• ➕ Добавить репозиторий: ввести owner/repo или GitHub URL\n"
    "  и выбрать режим отслеживания.\n"
    "• 📋 Мои подписки: список подписок чата с возможностью удалить.\n"
    "• 🔍 Проверить сейчас: поставить подписки в очередь на немедленный\n"
    "  опрос; уведомления придут после ближайшего цикла worker'a.\n"
    "• ⚙️ Настройки: язык сводки (ru/en), стиль (Кратко/Подробно)\n"
    "  и свободные пожелания к содержанию.\n\n"
    "Режимы отслеживания:\n"
    "• Releases: уведомление приходит при появлении нового GitHub-релиза.\n"
    "• File: уведомление приходит при изменении файла на default-ветке\n"
    "  (сравнение по blob sha).\n\n"
    "Сводки готовит LLM на выбранном языке. В первую очередь\n"
    "подсвечиваются breaking changes и ключевые изменения."
)


@router.callback_query(F.data == "menu:help")
async def help_message(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query()
async def stale_callback(callback: CallbackQuery, state: FSMContext) -> None:
    # Перехват для всех нажатий, которые не поймал ни один хендлер выше.
    # Бот хранит FSM-состояние в памяти (MemoryStorage) и теряет его при каждом
    # рестарте/переподключении. После этого кнопки, привязанные к состоянию
    # (например выбор режима add:mode:*), и любые кнопки из старых сообщений
    # перестают матчиться: без ответа на callback кнопка бесконечно крутит
    # спиннер и выглядит как «не работает». Здесь гасим спиннер и возвращаем
    # пользователя в актуальное меню.
    await state.clear()
    await callback.answer("Кнопка устарела, открыл актуальное меню.")
    if callback.message:
        await callback.message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())
