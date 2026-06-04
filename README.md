# Karipuza VPN Bot

Telegram-бот для выдачи VPN-ключей через Marzban.

## Что умеет

- `/start` и главное меню
- Тестовый доступ на 1 день
- Тест можно получить только один раз
- Автоматическая выдача ключа без ручного одобрения
- Кнопка копирования ключа
- Инструкция подключения
- Админ-уведомление о выдаче доступа
- Админ-кнопка отключения пользователя
- Подготовлено для будущих оплат через ЮKassa / Robokassa

## Файлы

```text
bot.py
config.py
database.py
keyboards.py
marzban_api.py
texts.py
requirements.txt
.env.example
.gitignore
deploy.sh
systemd/karipuza-bot.service
```

## Настройка .env

Скопируйте `.env.example` в `.env` и заполните:

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

## Запуск на сервере

```bash
cd /opt/karipuza-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 bot.py
```

## Обновление через Git

На ПК:

```bash
git add .
git commit -m "Update bot"
git push
```

На сервере:

```bash
cd /opt/karipuza-bot
git pull
systemctl restart karipuza-bot
```
