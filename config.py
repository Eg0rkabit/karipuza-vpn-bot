import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def parse_admin_ids(value: str) -> list[int]:
    admin_ids: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            admin_ids.append(int(item))
    return admin_ids


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: list[int]
    marzban_url: str
    marzban_username: str
    marzban_password: str
    marzban_inbound_tag: str
    public_host: str
    support_username: str


settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS", "")),
    marzban_url=os.getenv("MARZBAN_URL", "http://127.0.0.1:8000").strip().rstrip("/"),
    marzban_username=os.getenv("MARZBAN_USERNAME", "").strip(),
    marzban_password=os.getenv("MARZBAN_PASSWORD", "").strip(),
    marzban_inbound_tag=os.getenv("MARZBAN_INBOUND_TAG", "VLESS TCP REALITY").strip(),
    public_host=os.getenv("PUBLIC_HOST", "").strip(),
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
    if not settings.public_host:
        missing.append("PUBLIC_HOST")

    if missing:
        raise RuntimeError("Не заполнены переменные в .env: " + ", ".join(missing))
