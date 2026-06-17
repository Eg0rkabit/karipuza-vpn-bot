from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonCommands

from .config import settings, validate_settings
from .database import Database
from .handlers import create_router
from .middleware import CallbackThrottleMiddleware
from .remnawave import RemnawaveClient


async def configure_bot_menu(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="menu", description="Главное меню"),
            BotCommand(command="start", description="Перезапустить бота"),
            BotCommand(command="cancel", description="Отменить текущее действие"),
        ]
    )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def run() -> None:
    validate_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    db = Database(settings.database_path)
    await db.init()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    router = create_router(db, RemnawaveClient(settings), settings)
    router.callback_query.middleware(CallbackThrottleMiddleware(settings))
    dispatcher.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await configure_bot_menu(bot)
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
