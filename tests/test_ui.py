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

    def test_public_brand_is_karipaza_froxy(self) -> None:
        text = ui.main_text()
        buttons = [
            button.text
            for row in ui.main_keyboard(False, "https://example.com").inline_keyboard
            for button in row
        ]

        self.assertIn("Karipaza Froxy", text)
        self.assertNotIn("Karipuza VPN", text)
        self.assertIn("🚀 Karipaza Froxy", buttons)

    def test_main_menu_has_single_documents_button(self) -> None:
        keyboard = ui.main_keyboard(
            False,
            "https://app.example",
            "https://app.example/privacy",
            "https://app.example/terms",
        )
        buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
        ]

        document_buttons = [
            button
            for button in buttons
            if button.callback_data == "documents"
        ]
        self.assertEqual(len(document_buttons), 1)
        self.assertEqual(document_buttons[0].text, "📚 Документы")
        self.assertFalse(any(button.url for button in document_buttons))

    def test_documents_menu_contains_both_legal_pages(self) -> None:
        keyboard = ui.documents_keyboard(
            "https://app.example/privacy",
            "https://app.example/terms",
        )
        buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertTrue(
            any(
                button.text == "🔒 Политика конфиденциальности"
                and button.url == "https://app.example/privacy"
                for button in buttons
            )
        )
        self.assertTrue(
            any(
                button.text == "📄 Пользовательское соглашение"
                and button.url == "https://app.example/terms"
                for button in buttons
            )
        )

    def test_public_text_avoids_disallowed_positioning(self) -> None:
        text = ui.main_text()

        self.assertNotIn("свободному интернету", text.lower())
        self.assertIn("защищённое подключение", text.lower())

    def test_plan_requires_acceptance_and_links_documents(self) -> None:
        tariff = ui.TARIFFS[0]
        keyboard = ui.plan_keyboard(
            tariff,
            "https://app.example/privacy",
            "https://app.example/terms",
        )
        buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertIn("ознакомились", ui.plan_text(tariff))
        self.assertTrue(
            any(button.text == "✅ Принять и оформить" for button in buttons)
        )
        self.assertTrue(
            any(
                button.text == "📚 Политика и соглашение"
                and button.callback_data == "documents:plan:month_1"
                for button in buttons
            )
        )

    def test_user_profile_does_not_show_telegram_id(self) -> None:
        text = ui.profile_text("Егор", "egor", None)

        self.assertIn("@egor", text)
        self.assertNotIn("Telegram ID", text)
