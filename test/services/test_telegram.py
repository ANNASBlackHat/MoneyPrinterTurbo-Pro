import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.telegram import TelegramService, _chunk_text, _truncate


_CONFIG_BASE = {
    "telegram_enabled": True,
    "telegram_bot_token": "123456:test-token",
    "telegram_chat_id": "987654321",
}


def _mock_response(ok=True, description="Bad Request: test"):
    r = MagicMock()
    r.json.return_value = (
        {"ok": True, "result": {"message_id": 1}}
        if ok
        else {"ok": False, "description": description}
    )
    r.raise_for_status = MagicMock()
    return r


class TestTelegramHelpers(unittest.TestCase):
    def test_truncate_keeps_short_text(self):
        self.assertEqual(_truncate("short", 1024), "short")

    def test_truncate_limits_long_text(self):
        text = "x" * 2000
        result = _truncate(text, 10)
        self.assertLessEqual(len(result), 10)
        self.assertTrue(result.endswith("…"))

    def test_chunk_text_splits_long_script(self):
        text = "x" * 9000
        chunks = _chunk_text(text, 4096)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(c) <= 4096 for c in chunks))
        self.assertEqual("".join(chunks), text)

    def test_chunk_text_empty(self):
        self.assertEqual(_chunk_text(""), [])
        self.assertEqual(_chunk_text(None), [])


class TestTelegramService(unittest.TestCase):
    @patch(
        "app.services.telegram.config.app",
        {**_CONFIG_BASE, "telegram_enabled": False},
    )
    @patch("app.services.telegram.requests.post")
    def test_unconfigured_service_skips_request(self, mock_post):
        """功能未启用时不能消耗 Bot API 配额或抛出未预期异常。"""
        service = TelegramService()

        self.assertFalse(service.is_configured())
        result = service.send_message("hello")
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

        result = service.send_video("/fake/v.mp4", caption="Title")
        self.assertFalse(result["success"])
        mock_post.assert_not_called()

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=False)
    @patch("app.services.telegram.requests.post")
    def test_missing_video_skips_request(self, mock_post, _exists):
        """本地成片不存在时应在发起网络请求前返回明确错误。"""
        result = TelegramService().send_video("/missing/v.mp4")

        self.assertFalse(result["success"])
        self.assertIn("Video file not found", result["error"])
        mock_post.assert_not_called()

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.telegram.requests.post")
    def test_send_video_request_error_returns_failure(self, mock_post, _exists):
        """网络异常需要转换为稳定结果，不能中断调用方流程。"""
        mock_post.side_effect = requests.exceptions.Timeout("upload timed out")

        result = TelegramService().send_video("/fake/v.mp4", caption="Title")

        self.assertFalse(result["success"])
        self.assertIn("upload timed out", result["error"])

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.telegram.requests.post")
    def test_send_video_success(self, mock_post, _exists):
        mock_post.return_value = _mock_response(ok=True)

        result = TelegramService().send_video("/fake/v.mp4", caption="Title")

        self.assertTrue(result["success"])
        call_url = mock_post.call_args[0][0]
        self.assertTrue(call_url.endswith("/sendVideo"))
        self.assertIn(
            "123456:test-token", call_url, f"Unexpected endpoint: {call_url}"
        )
        data = mock_post.call_args[1]["data"]
        self.assertEqual(data["chat_id"], "987654321")
        self.assertEqual(data["caption"], "Title")

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.telegram.requests.post")
    def test_send_video_api_rejection_is_failure(self, mock_post, _exists):
        mock_post.return_value = _mock_response(ok=False, description="chat not found")

        result = TelegramService().send_video("/fake/v.mp4")

        self.assertFalse(result["success"])
        self.assertIn("chat not found", result["error"])

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.telegram.requests.post")
    def test_send_message_success(self, mock_post, _exists):
        mock_post.return_value = _mock_response(ok=True)

        result = TelegramService().send_message("hello script")

        self.assertTrue(result["success"])
        call_url = mock_post.call_args[0][0]
        self.assertTrue(call_url.endswith("/sendMessage"))
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["chat_id"], "987654321")
        self.assertEqual(payload["text"], "hello script")

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.telegram.requests.post")
    def test_send_video_with_script_sends_video_and_messages(self, mock_post, _exists):
        mock_post.return_value = _mock_response(ok=True)

        result = TelegramService().send_video_with_script(
            "/fake/v.mp4", "Subject", "line one\nline two"
        )

        self.assertTrue(result["success"])
        self.assertEqual(mock_post.call_count, 2)
        endpoints = [call[0][0] for call in mock_post.call_args_list]
        self.assertEqual(endpoints[0].split("/")[-1], "sendVideo")
        self.assertEqual(endpoints[1].split("/")[-1], "sendMessage")

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.telegram.requests.post")
    def test_send_video_with_script_long_script_is_chunked(self, mock_post, _exists):
        mock_post.return_value = _mock_response(ok=True)
        long_script = "x" * 9000

        result = TelegramService().send_video_with_script(
            "/fake/v.mp4", "Subject", long_script
        )

        self.assertTrue(result["success"])
        self.assertEqual(mock_post.call_count, 1 + 3)

    @patch("app.services.telegram.config.app", _CONFIG_BASE)
    @patch("app.services.telegram.os.path.exists", return_value=True)
    @patch("builtins.open", mock_open(read_data=b"fake"))
    @patch("app.services.telegram.requests.post")
    def test_send_video_with_script_partial_failure(self, mock_post, _exists):
        mock_post.side_effect = [
            _mock_response(ok=True),
            _mock_response(ok=False, description="message too long"),
        ]

        result = TelegramService().send_video_with_script(
            "/fake/v.mp4", "Subject", "script"
        )

        self.assertFalse(result["success"])
        self.assertIn("message too long", result["error"])


if __name__ == "__main__":
    unittest.main()
