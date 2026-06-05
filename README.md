# Karipuza VPN Bot Stable

Эта версия сделана стабильнее: главное меню теперь не inline, а обычная клавиатура Telegram.
Поэтому кнопки `🚀 Купить VPN` и `🔑 Мой ключ` обрабатываются как обычные сообщения и не должны "молчать".

## Что умеет

- `/start`
- `🚀 Купить VPN`
- `🔑 Мой ключ`
- `📲 Инструкция`
- `💬 Поддержка`
- Тест 1 день
- Тест можно получить только один раз
- Автоматическая выдача доступа через Marzban
- Выдача ссылки подписки Marzban, если она настроена
- Кнопка копирования ссылки без показа полной ссылки в сообщении
- Админ-уведомление
- Админ-кнопка отключения доступа
- Админский статус сервера через кнопку в админке или `/status`

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
SUBSCRIPTION_URL_PREFIX=https://vpn.example.com
SUBSCRIPTION_CHECK_HOST=sub.karipuza.ru

SUPPORT_USERNAME=@your_username
```

Если нужно включить в подписку несколько Reality inbound, укажите их через запятую:

```env
MARZBAN_INBOUND_TAGS=VLESS TCP REALITY,VLESS TCP REALITY APPLE TEST
```

Для подписок Marzban должен отдавать внешний HTTPS-адрес. Обычно это настраивается в `/opt/marzban/.env` через `XRAY_SUBSCRIPTION_URL_PREFIX`.

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
