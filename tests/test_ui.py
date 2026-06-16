from __future__ import annotations

import unittest

from karipuza_bot import ui


class UiTests(unittest.TestCase):
    def test_main_menu_contains_admin_button_only_for_admin(self) -> None:
        user_buttons = [
            button.text
            for row in ui.main_keyboard(False).inline_keyboard
            for button in row
        ]
        admin_buttons = [
            button.text
            for row in ui.main_keyboard(True).inline_keyboard
            for button in row
        ]

        self.assertFalse(any("Админ-панель" in text for text in user_buttons))
        self.assertTrue(any("Админ-панель" in text for text in admin_buttons))
        self.assertTrue(any("Профиль" in text for text in user_buttons))

    def test_user_name_is_escaped(self) -> None:
        text = ui.main_text("<Егор>")
        self.assertIn("&lt;Егор&gt;", text)
        self.assertNotIn("<Егор>", text)
