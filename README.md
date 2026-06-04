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
- Автоматическая выдача ключа через Marzban
- Кнопка копирования ключа без показа полного ключа в сообщении
- Админ-уведомление
- Админ-кнопка отключения доступа

## .env

```env
BOT_TOKEN=токен_от_BotFather
ADMIN_IDS=ваш_telegram_id

MARZBAN_URL=http://127.0.0.1:8000
MARZBAN_USERNAME=логин_Marzban
MARZBAN_PASSWORD=пароль_Marzban
MARZBAN_INBOUND_TAG=VLESS TCP REALITY
PUBLIC_HOST=176.124.220.50

SUPPORT_USERNAME=@your_username
```

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
