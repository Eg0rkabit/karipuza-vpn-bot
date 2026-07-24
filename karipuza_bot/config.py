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
    previous_price_rub: int
    marketing_label: str
    featured: bool = False

    @property
    def discount_percent(self) -> int:
        if self.previous_price_rub <= self.price_rub:
            return 0
        return round(
            (self.previous_price_rub - self.price_rub) * 100 / self.previous_price_rub
        )

    @property
    def badge(self) -> str:
        return f"Скидка {self.discount_percent}%"


TARIFFS: tuple[Tariff, ...] = (
    Tariff("month_1", "1 месяц", 30, 229, 299, "Лёгкий старт"),
    Tariff("month_3", "3 месяца", 90, 549, 799, "Популярный", True),
    Tariff("year_1", "1 год", 365, 1979, 2799, "Самый выгодный"),
)

TARIFFS_BY_CODE = {tariff.code: tariff for tariff in TARIFFS}


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    bot_username: str
    admin_ids: tuple[int, ...]
    database_path: Path

    mini_app_url: str
    webapp_host: str
    webapp_port: int
    webapp_dev_auth: bool
    webapp_auth_ttl_seconds: int
    mobile_auth_ttl_seconds: int
    mobile_session_ttl_days: int
    mobile_subscription_max_bytes: int
    mobile_subscription_allowed_hosts: tuple[str, ...]

    remnawave_url: str
    remnawave_api_token: str
    remnawave_squad_uuids: tuple[str, ...]

    payment_details: str
    yookassa_shop_id: str
    yookassa_secret_key: str
    yookassa_return_url: str

    action_cooldown_seconds: float
    heavy_action_cooldown_seconds: float
    subscription_device_limit: int = 5
    legal_support_contact: str = ""
    legal_effective_date: str = "24.07.2026"

    @property
    def remnawave_ready(self) -> bool:
        return bool(
            self.remnawave_url
            and self.remnawave_api_token
            and self.remnawave_squad_uuids
        )

    @property
    def yookassa_ready(self) -> bool:
        return bool(
            self.yookassa_shop_id
            and self.yookassa_secret_key
            and self.yookassa_return_url
        )

    def public_url(self, path: str) -> str:
        if not self.mini_app_url:
            return ""
        return f"{self.mini_app_url.rstrip('/')}/{path.lstrip('/')}"

    @property
    def privacy_url(self) -> str:
        return self.public_url("/privacy")

    @property
    def terms_url(self) -> str:
        return self.public_url("/terms")

    @property
    def documents_url(self) -> str:
        return self.public_url("/documents")


settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    bot_username=os.getenv("BOT_USERNAME", "").strip().lstrip("@"),
    admin_ids=_csv_ints(os.getenv("ADMIN_IDS", "")),
    database_path=Path(
        os.getenv("DATABASE_PATH", "/opt/karipuza-bot/data/karipuza.db")
    ),
    mini_app_url=os.getenv("MINI_APP_URL", "").strip().rstrip("/"),
    webapp_host=os.getenv("WEBAPP_HOST", "127.0.0.1").strip(),
    webapp_port=int(os.getenv("WEBAPP_PORT", "8080")),
    webapp_dev_auth=os.getenv("WEBAPP_DEV_AUTH", "").strip().lower()
    in {"1", "true", "yes", "on"},
    webapp_auth_ttl_seconds=int(os.getenv("WEBAPP_AUTH_TTL_SECONDS", "86400")),
    mobile_auth_ttl_seconds=int(os.getenv("MOBILE_AUTH_TTL_SECONDS", "600")),
    mobile_session_ttl_days=int(os.getenv("MOBILE_SESSION_TTL_DAYS", "180")),
    mobile_subscription_max_bytes=int(
        os.getenv("MOBILE_SUBSCRIPTION_MAX_BYTES", "2097152")
    ),
    mobile_subscription_allowed_hosts=_csv_strings(
        os.getenv("MOBILE_SUBSCRIPTION_ALLOWED_HOSTS", "sub.karipuza.ru").lower()
    ),
    remnawave_url=os.getenv("REMNAWAVE_URL", "http://127.0.0.1:3002")
    .strip()
    .rstrip("/"),
    remnawave_api_token=os.getenv("REMNAWAVE_API_TOKEN", "").strip(),
    remnawave_squad_uuids=_csv_strings(os.getenv("REMNAWAVE_SQUAD_UUIDS", "")),
    payment_details=_multiline(os.getenv("PAYMENT_DETAILS", "")),
    yookassa_shop_id=os.getenv("YOOKASSA_SHOP_ID", "").strip(),
    yookassa_secret_key=os.getenv("YOOKASSA_SECRET_KEY", "").strip(),
    yookassa_return_url=os.getenv("YOOKASSA_RETURN_URL", "").strip(),
    action_cooldown_seconds=float(os.getenv("ACTION_COOLDOWN_SECONDS", "0.8")),
    heavy_action_cooldown_seconds=float(
        os.getenv("HEAVY_ACTION_COOLDOWN_SECONDS", "3")
    ),
    subscription_device_limit=int(os.getenv("SUBSCRIPTION_DEVICE_LIMIT", "5")),
    legal_support_contact=os.getenv("LEGAL_SUPPORT_CONTACT", "").strip(),
    legal_effective_date=os.getenv("LEGAL_EFFECTIVE_DATE", "24.07.2026").strip(),
)


def validate_settings() -> None:
    missing: list[str] = []
    if not settings.bot_token:
        missing.append("BOT_TOKEN")
    if not settings.admin_ids:
        missing.append("ADMIN_IDS")
    if settings.subscription_device_limit < 1:
        raise RuntimeError("SUBSCRIPTION_DEVICE_LIMIT должен быть не меньше 1")
    if missing:
        raise RuntimeError("Не заполнены переменные в .env: " + ", ".join(missing))
