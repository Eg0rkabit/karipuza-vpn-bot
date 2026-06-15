from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _csv_ints(value: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in value.split(",") if item.strip())


def _csv_strings(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _multiline(value: str) -> str:
    return value.replace("\\n", "\n").strip()


@dataclass(frozen=True, slots=True)
class Tariff:
    code: str
    title: str
    days: int
    price_rub: int
    badge: str


TARIFFS: tuple[Tariff, ...] = (
    Tariff("month_1", "1 месяц", 30, 299, "Старт"),
    Tariff("month_3", "3 месяца", 90, 799, "Выгодно"),
    Tariff("month_6", "6 месяцев", 180, 1499, "Популярный"),
    Tariff("year_1", "1 год", 365, 2799, "Максимум"),
)

TARIFFS_BY_CODE = {tariff.code: tariff for tariff in TARIFFS}


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: tuple[int, ...]
    database_path: Path

    remnawave_url: str
    remnawave_api_token: str
    remnawave_squad_uuids: tuple[str, ...]

    payment_details: str

    action_cooldown_seconds: float
    heavy_action_cooldown_seconds: float

    @property
    def remnawave_ready(self) -> bool:
        return bool(
            self.remnawave_url
            and self.remnawave_api_token
            and self.remnawave_squad_uuids
        )


settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    admin_ids=_csv_ints(os.getenv("ADMIN_IDS", "")),
    database_path=Path(
        os.getenv("DATABASE_PATH", "/opt/karipuza-bot/data/karipuza.db")
    ),
    remnawave_url=os.getenv("REMNAWAVE_URL", "http://127.0.0.1:3002")
    .strip()
    .rstrip("/"),
    remnawave_api_token=os.getenv("REMNAWAVE_API_TOKEN", "").strip(),
    remnawave_squad_uuids=_csv_strings(os.getenv("REMNAWAVE_SQUAD_UUIDS", "")),
    payment_details=_multiline(os.getenv("PAYMENT_DETAILS", "")),
    action_cooldown_seconds=float(os.getenv("ACTION_COOLDOWN_SECONDS", "0.8")),
    heavy_action_cooldown_seconds=float(
        os.getenv("HEAVY_ACTION_COOLDOWN_SECONDS", "3")
    ),
)


def validate_settings() -> None:
    missing: list[str] = []
    if not settings.bot_token:
        missing.append("BOT_TOKEN")
    if not settings.admin_ids:
        missing.append("ADMIN_IDS")
    if missing:
        raise RuntimeError("Не заполнены переменные в .env: " + ", ".join(missing))
