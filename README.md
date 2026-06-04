# Karipuza VPN Bot

Telegram-бот для выдачи VPN-доступа через Marzban.

## Возможности первой версии

- `/start`
- кнопка «Купить VPN»
- выбор тарифа
- заявка админу
- админ подтверждает заявку кнопкой
- бот создаёт/обновляет пользователя в Marzban
- бот отправляет VLESS-ключ и инструкцию
- кнопка «Мой ключ»

## Локальный запуск

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

На Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 bot.py
```

## .env

```env
BOT_TOKEN=token_from_botfather
ADMIN_IDS=123456789

MARZBAN_URL=http://127.0.0.1:8000
MARZBAN_USERNAME=admin
MARZBAN_PASSWORD=password
MARZBAN_INBOUND_TAG=VLESS TCP REALITY
PUBLIC_HOST=176.124.220.50

SUPPORT_USERNAME=@your_username
```

## Обновление на VPS

```bash
cd /opt/karipuza-bot
git pull
source venv/bin/activate
pip install -r requirements.txt
systemctl restart karipuza-bot
```
