"""Telegram Bot API client. sendMessage with topic routing."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ..config import Config

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


def send(cfg: Config, topic: str, text: str) -> tuple[bool, int | None, str]:
    """Send to the named topic. Returns (ok, message_id, error_or_empty).

    thread_id 0 → omit message_thread_id (routes to General / main chat).
    """
    thread_id = cfg.topic_for(topic)
    url = API.format(token=cfg.tg_bot_token, method="sendMessage")
    payload = {
        "chat_id": cfg.tg_chat_id,
        "text": text,
        "disable_web_page_preview": False,
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    try:
        r = httpx.post(url, data=payload, timeout=15.0)
        j = r.json()
    except Exception as e:
        log.error("telegram send failed: %s", e)
        return False, None, str(e)

    if not j.get("ok"):
        return False, None, j.get("description", "unknown")
    return True, j["result"]["message_id"], ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
