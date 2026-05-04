from app.bot.keyboards import main_menu_keyboard, subscription_mode_keyboard


def test_main_menu_keyboard_contains_expected_actions() -> None:
    keyboard = main_menu_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [button.callback_data for button in buttons] == [
        "menu:add",
        "menu:subscriptions",
        "menu:check",
        "menu:settings",
        "menu:help",
    ]


def test_subscription_mode_keyboard_contains_expected_actions() -> None:
    keyboard = subscription_mode_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [button.callback_data for button in buttons] == [
        "add:mode:releases",
        "add:mode:file",
        "add:cancel",
    ]
