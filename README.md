# Karipuza VPN Bot

Рабочая версия Telegram-бота для Karipuza VPN + Marzban.

## Что умеет

- Главное меню
- Купить VPN
- Тест 1 день
- Тест можно использовать только один раз
- Автоматическая выдача ключа через Marzban без ручного одобрения
- Кнопка копирования ключа без показа полного ключа в сообщении
- Инструкция подключения
- Админ-уведомление о выдаче доступа
- Админ-кнопка отключения пользователя

## Важно

Кнопка копирования ключа использует Telegram `copy_text`.
У пользователя должен быть актуальный Telegram-клиент.

## Настройка

Создайте `.env` из `.env.example`:

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

## Запуск вручную

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
