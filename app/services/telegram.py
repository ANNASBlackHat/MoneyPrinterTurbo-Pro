"""
Telegram Bot API integration for sending generated videos after completion.

The service sends each final video to a configured chat or channel, with the
video subject as the caption and the generated script as follow-up messages.

Docs: https://core.telegram.org/bots/api
"""
import os
from typing import Optional

import requests
from loguru import logger

from app.config import config

# Telegram API limits: 1-1024 chars for video captions, 1-4096 chars for text
# messages. Texts beyond the message limit are split into multiple messages.
_CAPTION_LIMIT = 1024
_MESSAGE_LIMIT = 4096


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _chunk_text(text: str, limit: int = _MESSAGE_LIMIT) -> list[str]:
    if not text:
        return []
    return [text[i : i + limit] for i in range(0, len(text), limit)]


class TelegramService:
    API_BASE = "https://api.telegram.org"

    def __init__(self):
        self.enabled = config.app.get("telegram_enabled", False)
        self.bot_token = config.app.get("telegram_bot_token", "")
        self.chat_id = config.app.get("telegram_chat_id", "")

    def is_configured(self) -> bool:
        return bool(self.enabled and self.bot_token and self.chat_id)

    def _method_url(self, method: str) -> str:
        return f"{self.API_BASE}/bot{self.bot_token}/{method}"

    def _post(self, method: str, timeout: int, **kwargs) -> dict:
        """调用 Bot API 并把 Telegram 的 ok/description 收敛为统一返回。"""
        if not self.is_configured():
            logger.warning("Telegram is not configured. Skipping send.")
            return {"success": False, "error": "Telegram not configured"}

        try:
            response = requests.post(
                self._method_url(method),
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                logger.info(f"Telegram {method} sent successfully")
                return {"success": True}
            description = result.get("description") or "Unknown Telegram error"
            logger.warning(f"Telegram {method} failed: {description}")
            return {"success": False, "error": description}

        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to send Telegram {method}: {str(exc)}")
            return {"success": False, "error": str(exc)}

    def send_message(self, text: str) -> dict:
        if not text:
            return {"success": True}
        return self._post(
            "sendMessage",
            timeout=60,
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )

    def send_video(self, video_path: str, caption: Optional[str] = None) -> dict:
        if not self.is_configured():
            return {"success": False, "error": "Telegram not configured"}

        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return {"success": False, "error": f"Video file not found: {video_path}"}

        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = _truncate(caption, _CAPTION_LIMIT)

        try:
            with open(video_path, "rb") as video_file:
                response = requests.post(
                    self._method_url("sendVideo"),
                    data=data,
                    files={"video": video_file},
                    timeout=300,
                )
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                logger.success(f"Telegram video sent successfully: {video_path}")
                return {"success": True}
            description = result.get("description") or "Unknown Telegram error"
            logger.warning(f"Telegram sendVideo failed: {description}")
            return {"success": False, "error": description}

        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to send Telegram video: {str(exc)}")
            return {"success": False, "error": str(exc)}

    def send_video_with_script(
        self,
        video_path: str,
        video_subject: str,
        video_script: str,
    ) -> dict:
        """发送成片，并把脚本文本作为后续消息发出。"""
        results = [self.send_video(video_path, caption=video_subject or None)]
        for chunk in _chunk_text(video_script or ""):
            results.append(self.send_message(chunk))

        failures = [result for result in results if not result.get("success")]
        if failures:
            error_messages = [
                str(result.get("error") or "unknown telegram error")
                for result in failures
            ]
            return {"success": False, "error": "; ".join(error_messages)}
        return {"success": True}


# Singleton instance
telegram_service = TelegramService()


def send_telegram_video(
    video_path: str,
    video_subject: str,
    video_script: str,
) -> dict:
    return telegram_service.send_video_with_script(
        video_path,
        video_subject,
        video_script,
    )
