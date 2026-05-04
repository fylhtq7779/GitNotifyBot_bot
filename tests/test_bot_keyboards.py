from app.bot.keyboards import main_menu_keyboard


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
