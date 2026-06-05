# Karipuza VPN Bot

Бот для выдачи VPN-доступа через Marzban. Основное меню работает через inline-кнопки:
пользователь нажимает кнопки, а бот обновляет текущее сообщение вместо того, чтобы засорять чат.

## Что умеет

- `/start`
- `🚀 Купить VPN`
- `🔗 Моя подписка`
- `👤 Профиль`
- `📲 Инструкция`
- `💬 Поддержка`
- Тест 1 день
- Тест можно получить только один раз
- Автоматическая выдача доступа через Marzban
- Выдача ссылки подписки Marzban, если она настроена, с запасной прямой ссылкой доступа
- Кнопка копирования ссылки без показа полной ссылки в сообщении
- Напоминания пользователю за 3 дня, за 1 день и после окончания доступа
- Админ-уведомление
- Админ-кнопка отключения доступа
- Админский статус сервера через кнопку в админке или `/status`
- Старые текстовые кнопки поддерживаются как запасной вариант

## .env

```env
BOT_TOKEN=токен_от_BotFather
ADMIN_IDS=ваш_telegram_id

MARZBAN_URL=http://127.0.0.1:8000
MARZBAN_USERNAME=логин_Marzban
MARZBAN_PASSWORD=пароль_Marzban
MARZBAN_INBOUND_TAG=VLESS TCP REALITY
MARZBAN_INBOUND_TAGS=VLESS TCP REALITY
PUBLIC_HOST=176.124.220.50
SUBSCRIPTION_URL_PREFIX=https://sub.karipuza.ru:8443

SUPPORT_USERNAME=@your_username
```

Если нужно включить в подписку несколько Reality inbound, укажите их через запятую:

```env
MARZBAN_INBOUND_TAGS=VLESS TCP REALITY,VLESS TCP REALITY APPLE TEST
```

Для подписок Marzban должен отдавать внешний HTTPS-адрес. Обычно это настраивается в `/opt/marzban/.env` через `XRAY_SUBSCRIPTION_URL_PREFIX`.

## HTTPS-подписки

DNS `sub.karipuza.ru` должен вести на VPS. Reality использует порт `443`, поэтому подписки выдаются через отдельный HTTPS-порт `8443`:

```bash
cd /opt/karipuza-bot
git pull
bash scripts/setup-subscription-https.sh
```

Скрипт настраивает nginx, Let's Encrypt, `XRAY_SUBSCRIPTION_URL_PREFIX=https://sub.karipuza.ru:8443` в Marzban и `SUBSCRIPTION_URL_PREFIX=https://sub.karipuza.ru:8443` в боте.

## Запуск

```bash
cd /opt/karipuza-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 bot.py
```

## Автозапуск

```bash
cp systemd/karipuza-bot.service /etc/systemd/system/karipuza-bot.service
systemctl daemon-reload
systemctl enable karipuza-bot
systemctl restart karipuza-bot
systemctl status karipuza-bot
```

## Логи

```bash
journalctl -u karipuza-bot -f
```
