import json
import sys
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

ROOT_DIR = Path(__file__).parent.parent.parent
WEBUI_MAIN = ROOT_DIR / "webui" / "Main.py"
I18N_DIR = ROOT_DIR / "webui" / "i18n"
TEST_LOCALES = ("en", "zh")


class TestWebuiTelegramSettings(unittest.TestCase):
    @staticmethod
    def _translation(locale, key):
        locale_data = json.loads(
            (I18N_DIR / f"{locale}.json").read_text(encoding="utf-8")
        )
        return locale_data["Translation"][key]

    def _open_settings_dialog(self, locale):
        app = AppTest.from_file(str(WEBUI_MAIN), default_timeout=30)
        # 显式覆盖会话语言并打开设置弹窗，跳过 CI 无 config.toml 的语言依赖。
        app.session_state["ui_language"] = locale
        app.session_state["settings_dialog_open"] = True
        app.run()
        return app

    def _widget_by_key(self, elements, key):
        widget = next(
            (
                item
                for item in elements
                if str(getattr(item, "key", "")) == key
                or str(getattr(item, "key", "")).startswith(f"{key}_")
            ),
            None,
        )
        self.assertIsNotNone(widget, f"widget not found: {key}")
        return widget

    def test_publishing_tab_and_telegram_settings_render(self):
        for locale in TEST_LOCALES:
            with self.subTest(locale=locale):
                app = self._open_settings_dialog(locale)
                self.assertEqual([str(item.value) for item in app.exception], [])

                tab_labels = [tab.label for tab in app.tabs]
                self.assertIn(self._translation(locale, "Publishing Settings Tab"), tab_labels)

                self._widget_by_key(app.checkbox, "telegram_enabled_checkbox")
                self._widget_by_key(app.text_input, "telegram_bot_token_input")
                self._widget_by_key(app.text_input, "telegram_chat_id_input")


if __name__ == "__main__":
    unittest.main()