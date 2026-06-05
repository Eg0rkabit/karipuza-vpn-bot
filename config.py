import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def parse_admin_ids(value: str) -> list[int]:
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            result.append(int(item))
    return result


def parse_inbound_tags(value: str) -> list[str]:
    result: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            result.append(item)
    return result


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: list[int]

    marzban_url: str
    marzban_username: str
    marzban_password: str
    marzban_inbound_tag: str
    marzban_inbound_tags: list[str]
    public_host: str
    subscription_url_prefix: str

    support_username: str


primary_inbound_tag = os.getenv("MARZBAN_INBOUND_TAG", "VLESS TCP REALITY").strip()
inbound_tags = parse_inbound_tags(os.getenv("MARZBAN_INBOUND_TAGS", primary_inbound_tag))

settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS", "")),

    marzban_url=os.getenv("MARZBAN_URL", "http://127.0.0.1:8000").strip().rstrip("/"),
    marzban_username=os.getenv("MARZBAN_USERNAME", "").strip(),
    marzban_password=os.getenv("MARZBAN_PASSWORD", "").strip(),
    marzban_inbound_tag=primary_inbound_tag,
    marzban_inbound_tags=inbound_tags,
    public_host=os.getenv("PUBLIC_HOST", "176.124.220.50").strip(),
    subscription_url_prefix=os.getenv("SUBSCRIPTION_URL_PREFIX", "").strip().rstrip("/"),

    support_username=os.getenv("SUPPORT_USERNAME", "@support").strip(),
)


def validate_settings() -> None:
    missing: list[str] = []

    if not settings.bot_token:
        missing.append("BOT_TOKEN")
    if not settings.admin_ids:
        missing.append("ADMIN_IDS")
    if not settings.marzban_username:
        missing.append("MARZBAN_USERNAME")
    if not settings.marzban_password:
        missing.append("MARZBAN_PASSWORD")
    if not settings.marzban_inbound_tags:
        missing.append("MARZBAN_INBOUND_TAGS")
    if not settings.public_host:
        missing.append("PUBLIC_HOST")

    if missing:
        raise RuntimeError("Не заполнены переменные в .env: " + ", ".join(missing))

    if settings.subscription_url_prefix and not settings.subscription_url_prefix.startswith(("http://", "https://")):
        raise RuntimeError("SUBSCRIPTION_URL_PREFIX должен начинаться с http:// или https://")
