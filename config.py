import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Не задана переменная окружения {name}. Проверь .env")
    return value


def _get_admin_ids() -> list[int]:
    raw = os.getenv("ADMIN_IDS", "")
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    if not ids:
        raise RuntimeError("Не задан ADMIN_IDS в .env")
    return ids


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: list[int]
    marzban_url: str
    marzban_username: str
    marzban_password: str
    marzban_inbound_tag: str
    public_host: str | None
    support_username: str


settings = Settings(
    bot_token=_get_required("BOT_TOKEN"),
    admin_ids=_get_admin_ids(),
    marzban_url=os.getenv("MARZBAN_URL", "http://127.0.0.1:8000").rstrip("/"),
    marzban_username=_get_required("MARZBAN_USERNAME"),
    marzban_password=_get_required("MARZBAN_PASSWORD"),
    marzban_inbound_tag=os.getenv("MARZBAN_INBOUND_TAG", "VLESS TCP REALITY"),
    public_host=os.getenv("PUBLIC_HOST") or None,
    support_username=os.getenv("SUPPORT_USERNAME", "@support"),
)
