from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from .config import Settings


class CallbackThrottleMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_action: dict[tuple[int, str], float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery) or not event.from_user:
            return await handler(event, data)

        callback_data = event.data or ""
        heavy = callback_data.startswith(
            (
                "subscription",
                "order:create:",
                "admin:order:approve:",
                "admin:user:grant:",
                "admin:user:enable:",
                "admin:user:disable:",
            )
        )
        bucket = "heavy" if heavy else "normal"
        cooldown = (
            self.settings.heavy_action_cooldown_seconds
            if heavy
            else self.settings.action_cooldown_seconds
        )
        key = (event.from_user.id, bucket)
        now = time.monotonic()

        if now - self.last_action[key] < cooldown:
            await event.answer("Подождите немного.", show_alert=False)
            return None

        self.last_action[key] = now
        return await handler(event, data)
